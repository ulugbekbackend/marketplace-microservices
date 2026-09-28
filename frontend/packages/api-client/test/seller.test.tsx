import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { loginErrorKey, retryAfterSeconds, errorDetail } from '../src/authErrors'
import { createApiClient } from '../src/client'
import { ApiError, CLIENT_ERROR } from '../src/errors'
import { ApiProvider } from '../src/hooks/context'
import { queryKeys } from '../src/hooks/keys'
import {
  useApplySeller,
  useSellerApplication,
  useSellerProduct,
  useSellerProducts,
  useUpdateVariantStock,
} from '../src/hooks/seller'
import { TokenStore } from '../src/tokens'
import type { SellerProductDetail } from '../src/types'
import { uploadWithProgress } from '../src/upload'
import { deferred, errorBody, fakeFetch, json, memoryStorage, type Handler } from './fakeServer'

const variant = {
  id: 'v1',
  sku: 'ATLAS-S',
  price_tiyin: 25_000_000,
  stock: 10,
  reserved: 3,
  available: 7,
  is_active: true,
  attributes: [],
  created_at: '2026-09-01T10:00:00Z',
  updated_at: '2026-09-01T10:00:00Z',
}

const product: SellerProductDetail = {
  id: 'p1',
  slug: 'atlas',
  title: "Atlas ko'ylak",
  status: 'active',
  category: { id: 'c1', name: 'Kiyim', slug: 'kiyim' },
  min_price_tiyin: 25_000_000,
  max_price_tiyin: 25_000_000,
  in_stock: true,
  variants_count: 1,
  image_url: null,
  created_at: '2026-09-01T10:00:00Z',
  updated_at: '2026-09-01T10:00:00Z',
  description: '',
  variants: [variant],
  images: [],
}

function setup(routes: Record<string, Handler>) {
  const server = fakeFetch(routes)
  const client = createApiClient({
    baseUrl: 'http://api.test',
    tokens: new TokenStore(memoryStorage({ 'bozorcha.refresh': 'r1' })),
    fetch: server.fetch,
  })
  client.tokens.set({ access: 'a1', refresh: 'r1' })
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={client}>{children}</ApiProvider>
    </QueryClientProvider>
  )
  return { server, client, queryClient, wrapper }
}

describe('seller application hooks', () => {
  it('treats 404 as "never applied" and seeds the cache after applying', async () => {
    const application = {
      id: 'a1',
      shop_name: 'Atlas uyi',
      inn: '123456789',
      description: '',
      status: 'pending',
      reviewed_at: null,
      created_at: '2026-09-01T10:00:00Z',
    }
    const { wrapper, server, queryClient } = setup({
      'GET /api/auth/seller/application/': () => json(404, errorBody('NOT_FOUND')),
      'POST /api/auth/seller/apply/': () => json(201, application),
    })
    const { result } = renderHook(
      () => ({ application: useSellerApplication(), apply: useApplySeller() }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.application.isSuccess).toBe(true))
    expect(result.current.application.data).toBeNull()

    await act(() => result.current.apply.mutateAsync({ shop_name: 'Atlas uyi', inn: '123456789' }))
    expect(server.callsTo('POST', '/api/auth/seller/apply/')[0]!.body).toEqual({
      shop_name: 'Atlas uyi',
      inn: '123456789',
    })
    expect(queryClient.getQueryData(queryKeys.sellerApplication)).toEqual(application)
  })

  it('surfaces other errors', async () => {
    const { wrapper } = setup({
      'GET /api/auth/seller/application/': () => json(500, errorBody('BOOM')),
    })
    const { result } = renderHook(() => useSellerApplication(), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error?.code).toBe('BOOM')
  })
})

describe('seller catalog hooks', () => {
  it('lists products with search, status and page as query params', async () => {
    const { wrapper, server } = setup({
      'GET /api/catalog/seller/products/': () =>
        json(200, { items: [], total: 0, page: 2, page_size: 20 }),
    })
    const { result } = renderHook(
      () => useSellerProducts({ q: 'atlas', status: 'draft', page: 2, page_size: 20 }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const url = server.callsTo('GET', '/api/catalog/seller/products/')[0]!.url
    expect(Object.fromEntries(url.searchParams)).toEqual({
      q: 'atlas',
      status: 'draft',
      page: '2',
      page_size: '20',
    })
  })

  it('loads a product by id', async () => {
    const { wrapper } = setup({ 'GET /api/catalog/seller/products/p1/': () => json(200, product) })
    const { result } = renderHook(() => useSellerProduct('p1'), { wrapper })
    await waitFor(() => expect(result.current.data?.title).toBe("Atlas ko'ylak"))
  })

  it('updates stock optimistically and keeps the server copy', async () => {
    const release = deferred()
    const { wrapper, queryClient, server } = setup({
      'PATCH /api/catalog/seller/variants/v1/stock/': async () => {
        await release.promise
        return json(200, { ...variant, stock: 15, available: 12 })
      },
    })
    queryClient.setQueryData(queryKeys.sellerProduct('p1'), product)
    const { result } = renderHook(() => useUpdateVariantStock(), { wrapper })

    act(() => result.current.mutate({ productId: 'p1', variantId: 'v1', stock: 15 }))
    await waitFor(() =>
      expect(
        queryClient.getQueryData<SellerProductDetail>(queryKeys.sellerProduct('p1'))!.variants[0],
      ).toMatchObject({ stock: 15, available: 12 }),
    )
    release.resolve()
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(server.callsTo('PATCH', '/api/catalog/seller/variants/v1/stock/')[0]!.body).toEqual({
      stock: 15,
    })
  })

  it('rolls back when the server refuses the stock', async () => {
    const { wrapper, queryClient } = setup({
      'PATCH /api/catalog/seller/variants/v1/stock/': () =>
        json(409, errorBody('STOCK_BELOW_RESERVED', 'below', { reserved: 3 })),
    })
    queryClient.setQueryData(queryKeys.sellerProduct('p1'), product)
    const { result } = renderHook(() => useUpdateVariantStock(), { wrapper })
    await act(async () => {
      await result.current
        .mutateAsync({ productId: 'p1', variantId: 'v1', stock: 1 })
        .catch(() => undefined)
    })
    await waitFor(() => expect(result.current.error?.code).toBe('STOCK_BELOW_RESERVED'))
    expect(errorDetail(result.current.error, 'reserved')).toBe(3)
    expect(
      queryClient.getQueryData<SellerProductDetail>(queryKeys.sellerProduct('p1'))!.variants[0]!
        .stock,
    ).toBe(10)
  })
})

describe('auth error helpers', () => {
  it('maps OTP errors and reads retry_after', () => {
    expect(loginErrorKey(new ApiError(400, 'OTP_INVALID', 'x'))).toBe('OTP_INVALID')
    expect(loginErrorKey(new ApiError(429, 'SOMETHING', 'x'))).toBe('OTP_RATE_LIMITED')
    expect(loginErrorKey(new ApiError(0, CLIENT_ERROR.NETWORK, 'x'))).toBe('network')
    expect(loginErrorKey(new Error('x'))).toBe('unknown')
    expect(retryAfterSeconds(new ApiError(429, 'X', 'x', { retry_after: 12.2 }))).toBe(13)
    expect(retryAfterSeconds(new ApiError(429, 'X', 'x', null))).toBeNull()
    expect(errorDetail('nope', 'reserved')).toBeUndefined()
  })
})

/** Minimal XHR double driven by the test. */
class FakeXhr {
  static last: FakeXhr | null = null
  method = ''
  url = ''
  headers: Record<string, string> = {}
  status = 0
  sent: unknown = null
  aborted = false
  upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  onabort: (() => void) | null = null
  constructor() {
    FakeXhr.last = this
  }
  open(method: string, url: string) {
    this.method = method
    this.url = url
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value
  }
  send(body: unknown) {
    this.sent = body
  }
  abort() {
    this.aborted = true
    this.onabort?.()
  }
  progress(loaded: number, total: number) {
    this.upload.onprogress?.({ lengthComputable: true, loaded, total } as ProgressEvent)
  }
  respond(status: number) {
    this.status = status
    this.onload?.()
  }
}

const createXhr = () => new FakeXhr() as unknown as XMLHttpRequest

describe('uploadWithProgress', () => {
  it('PUTs the body with the signed headers and reports progress', async () => {
    const progress: number[] = []
    const file = new Blob(['x'], { type: 'image/png' })
    const done = uploadWithProgress({
      url: 'http://s3.test/put',
      body: file,
      headers: { 'Content-Type': 'image/png' },
      onProgress: (fraction) => progress.push(fraction),
      createXhr,
    })
    const xhr = FakeXhr.last!
    expect(xhr.method).toBe('PUT')
    expect(xhr.headers).toEqual({ 'Content-Type': 'image/png' })
    expect(xhr.sent).toBe(file)
    xhr.progress(50, 100)
    xhr.respond(200)
    await done
    expect(progress).toEqual([0.5, 1])
  })

  it('rejects with the storage status, network error or abort', async () => {
    const failed = uploadWithProgress({ url: 'http://s3.test', body: new Blob(), createXhr })
    FakeXhr.last!.respond(403)
    await expect(failed).rejects.toMatchObject({ status: 403, code: 'HTTP_403' })

    const offline = uploadWithProgress({ url: 'http://s3.test', body: new Blob(), createXhr })
    FakeXhr.last!.onerror?.()
    await expect(offline).rejects.toMatchObject({ code: CLIENT_ERROR.NETWORK })

    const controller = new AbortController()
    const aborted = uploadWithProgress({
      url: 'http://s3.test',
      body: new Blob(),
      signal: controller.signal,
      createXhr,
    })
    controller.abort()
    await expect(aborted).rejects.toMatchObject({ code: CLIENT_ERROR.ABORTED })
    expect(FakeXhr.last!.aborted).toBe(true)
  })
})
