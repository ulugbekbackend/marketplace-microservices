import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { createApiClient } from '../src/client'
import { isApiError } from '../src/errors'
import { ApiProvider } from '../src/hooks/context'
import { queryKeys } from '../src/hooks/keys'
import { useInitPayment, useMockPayment, useSellerPayouts } from '../src/hooks/payments'
import { TokenStore } from '../src/tokens'
import type { Paginated, SellerPayout } from '../src/types'
import { errorBody, fakeFetch, json, memoryStorage, type Handler } from './fakeServer'

const ORDER = '0191f2a8-0000-7000-8000-000000000001'

function setup(routes: Record<string, Handler>) {
  const server = fakeFetch(routes)
  const client = createApiClient({
    baseUrl: 'http://api.test',
    tokens: new TokenStore(memoryStorage()),
    fetch: server.fetch,
  })
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={client}>{children}</ApiProvider>
    </QueryClientProvider>
  )
  return { server, wrapper, queryClient }
}

const payout = (period_start: string): SellerPayout => ({
  id: `p-${period_start}`,
  period_start,
  period_end: period_start,
  gross_tiyin: 1_000_000,
  commission_tiyin: 100_000,
  net_tiyin: 900_000,
  status: 'pending',
  lines_count: 2,
  created_at: '2026-10-05T00:00:00Z',
})

describe('useInitPayment', () => {
  it('posts the provider and returns where to go', async () => {
    const path = `/api/payments/${ORDER}/init/`
    const { server, wrapper } = setup({
      [`POST ${path}`]: () => json(200, { redirect_url: 'https://checkout.example/abc' }),
    })
    const { result } = renderHook(() => useInitPayment(), { wrapper })

    let answer: { redirect_url: string } | undefined
    await act(async () => {
      answer = await result.current.mutateAsync({ orderId: ORDER, provider: 'click' })
    })

    expect(answer).toEqual({ redirect_url: 'https://checkout.example/abc' })
    expect(server.callsTo('POST', path)[0]!.body).toEqual({ provider: 'click' })
  })

  it('surfaces ORDER_NOT_PAYABLE as an ApiError', async () => {
    const path = `/api/payments/${ORDER}/init/`
    const { wrapper } = setup({
      [`POST ${path}`]: () =>
        json(409, errorBody('ORDER_NOT_PAYABLE', 'nope', { status: 'EXPIRED' })),
    })
    const { result } = renderHook(() => useInitPayment(), { wrapper })

    act(() => result.current.mutate({ orderId: ORDER, provider: 'payme' }))

    await waitFor(() => expect(result.current.isError).toBe(true))
    const error = result.current.error
    expect(isApiError(error) && error.code).toBe('ORDER_NOT_PAYABLE')
  })
})

describe('useMockPayment', () => {
  it('drops the order and cart caches so the new status is read', async () => {
    const path = `/api/payments/mock/${ORDER}/pay`
    const { wrapper, queryClient } = setup({
      [`POST ${path}`]: () =>
        json(200, { transaction_id: 't1', order_id: ORDER, amount_tiyin: 100 }),
    })
    queryClient.setQueryData(queryKeys.orderStatus(ORDER), { status: 'RESERVED' })
    const { result } = renderHook(() => useMockPayment(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ orderId: ORDER })
    })

    expect(queryClient.getQueryState(queryKeys.orderStatus(ORDER))?.isInvalidated).toBe(true)
  })
})

describe('useSellerPayouts', () => {
  it('reads one page of payouts', async () => {
    const path = '/api/payments/seller/payouts/'
    const page: Paginated<SellerPayout> = {
      items: [payout('2026-09-28')],
      total: 3,
      page: 2,
      page_size: 1,
    }
    const { server, wrapper } = setup({ [`GET ${path}`]: () => json(200, page) })
    const { result } = renderHook(() => useSellerPayouts({ page: 2, page_size: 1 }), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(page)
    const url = server.callsTo('GET', path)[0]!.url
    expect(url.searchParams.get('page')).toBe('2')
    expect(url.searchParams.get('page_size')).toBe('1')
  })
})
