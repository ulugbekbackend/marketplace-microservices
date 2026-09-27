import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { createApiClient } from '../src/client'
import { ApiError } from '../src/errors'
import { useLogout } from '../src/hooks/auth'
import {
  EMPTY_CART,
  findCartItem,
  useAddToCart,
  useCart,
  useClearCart,
  useFavorites,
  useMergeCart,
  useRemoveCartItem,
  useToggleFavorite,
  useUpdateCartItem,
} from '../src/hooks/cart'
import { ApiProvider } from '../src/hooks/context'
import { queryKeys } from '../src/hooks/keys'
import { REFRESH_TOKEN_KEY, TokenStore } from '../src/tokens'
import type { Cart, CartItem } from '../src/types'
import { deferred, errorBody, fakeFetch, json, memoryStorage, type Handler } from './fakeServer'

const item = (variantId: string, qty: number, price = 10_000_00): CartItem => ({
  variant_id: variantId,
  product_id: `p-${variantId}`,
  product_slug: `slug-${variantId}`,
  title: `Product ${variantId}`,
  sku: `SKU-${variantId}`,
  image_url: null,
  attributes: [],
  qty,
  price_tiyin: price,
  line_total_tiyin: price * qty,
  available_qty: 10,
  available: true,
  price_changed: false,
  previous_price_tiyin: null,
})

const cartWith = (...items: CartItem[]): Cart => ({
  ...EMPTY_CART,
  groups: items.length
    ? [
        {
          seller_id: 's1',
          shop_name: 'Atlas',
          items,
          subtotal_tiyin: items.reduce((sum, i) => sum + i.line_total_tiyin, 0),
        },
      ]
    : [],
  items_count: items.reduce((sum, i) => sum + i.qty, 0),
  total_tiyin: items.reduce((sum, i) => sum + i.line_total_tiyin, 0),
})

function setup(routes: Record<string, Handler>, opts: { signedIn?: boolean } = {}) {
  const server = fakeFetch(routes)
  const storage = memoryStorage(opts.signedIn ? { [REFRESH_TOKEN_KEY]: 'r1' } : {})
  const client = createApiClient({
    baseUrl: 'http://api.test',
    tokens: new TokenStore(storage),
    fetch: server.fetch,
  })
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

describe('cart hooks', () => {
  it('loads the cart with credentials so the guest cookie travels cross-origin', async () => {
    const { wrapper, server } = setup({
      'GET /api/cart/': () => json(200, cartWith(item('v1', 2))),
    })
    const { result } = renderHook(() => useCart(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.items_count).toBe(2)
    expect(server.callsTo('GET', '/api/cart/')[0]!.credentials).toBe('include')
  })

  it('does not send credentials to other services', async () => {
    const { client, server } = setup({ 'GET /api/catalog/categories/': () => json(200, []) })
    await client.get('/api/catalog/categories/')
    expect(server.calls[0]!.credentials).toBeUndefined()
  })

  it('add / update / remove replace the cached cart with the response', async () => {
    const { wrapper, server, queryClient } = setup({
      'GET /api/cart/': () => json(200, EMPTY_CART),
      'POST /api/cart/items/': (req) => {
        const { variant_id, qty } = req.body as { variant_id: string; qty: number }
        return json(200, cartWith(item(variant_id, qty)))
      },
      'PATCH /api/cart/items/v1/': (req) =>
        json(200, cartWith(item('v1', (req.body as { qty: number }).qty))),
      'DELETE /api/cart/items/v1/': () => json(200, EMPTY_CART),
    })
    const { result } = renderHook(
      () => ({
        cart: useCart(),
        add: useAddToCart(),
        update: useUpdateCartItem(),
        remove: useRemoveCartItem(),
      }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.cart.isSuccess).toBe(true))

    await act(() => result.current.add.mutateAsync({ variantId: 'v1', qty: 3 }))
    expect(server.callsTo('POST', '/api/cart/items/')[0]!.body).toEqual({
      variant_id: 'v1',
      qty: 3,
    })
    await waitFor(() => expect(result.current.cart.data?.items_count).toBe(3))

    await act(() => result.current.update.mutateAsync({ variantId: 'v1', qty: 5 }))
    await waitFor(() => expect(findCartItem(result.current.cart.data, 'v1')?.qty).toBe(5))
    expect(server.callsTo('PATCH', '/api/cart/items/v1/')[0]!.credentials).toBe('include')

    await act(() => result.current.remove.mutateAsync({ variantId: 'v1' }))
    expect(queryClient.getQueryData(queryKeys.cart)).toEqual(EMPTY_CART)
    // no extra GETs: mutations write the cache directly
    expect(server.callsTo('GET', '/api/cart/')).toHaveLength(1)
  })

  it('runs cart mutations one at a time, in order', async () => {
    const first = deferred()
    const { wrapper, server, queryClient } = setup({
      'PATCH /api/cart/items/v1/': async (req) => {
        const { qty } = req.body as { qty: number }
        if (qty === 2) await first.promise
        return json(200, cartWith(item('v1', qty)))
      },
    })
    const { result } = renderHook(() => useUpdateCartItem(), { wrapper })
    act(() => {
      result.current.mutate({ variantId: 'v1', qty: 2 })
      result.current.mutate({ variantId: 'v1', qty: 3 })
    })
    await waitFor(() => expect(server.calls).toHaveLength(1))
    // the second request waits for the first
    await new Promise((r) => setTimeout(r, 20))
    expect(server.calls).toHaveLength(1)
    first.resolve()
    await waitFor(() => expect(server.calls).toHaveLength(2))
    await waitFor(() =>
      expect(findCartItem(queryClient.getQueryData(queryKeys.cart), 'v1')?.qty).toBe(3),
    )
  })

  it('refetches the cart when a mutation says it is out of date', async () => {
    let gets = 0
    const { wrapper, server } = setup({
      'GET /api/cart/': () => {
        gets += 1
        return json(200, cartWith(item('v1', 1)))
      },
      'PATCH /api/cart/items/v1/': () =>
        json(409, errorBody('OUT_OF_STOCK', 'Not enough stock', { available: 1 })),
    })
    const { result } = renderHook(() => ({ cart: useCart(), update: useUpdateCartItem() }), {
      wrapper,
    })
    await waitFor(() => expect(result.current.cart.isSuccess).toBe(true))
    const error = await act(() =>
      result.current.update.mutateAsync({ variantId: 'v1', qty: 4 }).catch((e: unknown) => e),
    )
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('OUT_OF_STOCK')
    expect((error as ApiError).details).toEqual({ available: 1 })
    await waitFor(() => expect(gets).toBe(2))
    expect(server.callsTo('GET', '/api/cart/')).toHaveLength(2)
  })

  it('clear empties the cache without a refetch', async () => {
    const { wrapper, queryClient } = setup({
      'DELETE /api/cart/': () => new Response(null, { status: 204 }),
    })
    queryClient.setQueryData(queryKeys.cart, cartWith(item('v1', 1)))
    const { result } = renderHook(() => useClearCart(), { wrapper })
    await act(() => result.current.mutateAsync())
    expect(queryClient.getQueryData(queryKeys.cart)).toEqual(EMPTY_CART)
  })

  it('merge stores the merged cart; a failed merge refetches instead', async () => {
    const merged = cartWith(item('v1', 1), item('v2', 2))
    let mergeOk = true
    const { wrapper, queryClient, server } = setup(
      {
        'POST /api/cart/merge/': () =>
          mergeOk ? json(200, merged) : json(503, errorBody('CATALOG_UNAVAILABLE')),
        'GET /api/cart/': () => json(200, cartWith(item('v9', 1))),
      },
      { signedIn: true },
    )
    const { result } = renderHook(() => ({ cart: useCart(), merge: useMergeCart() }), { wrapper })
    await waitFor(() => expect(result.current.cart.isSuccess).toBe(true))

    await act(() => result.current.merge.mutateAsync())
    expect(queryClient.getQueryData(queryKeys.cart)).toEqual(merged)
    expect(server.callsTo('POST', '/api/cart/merge/')[0]!.credentials).toBe('include')

    mergeOk = false
    await act(() => result.current.merge.mutateAsync().catch(() => undefined))
    await waitFor(() => expect(findCartItem(result.current.cart.data, 'v9')).toBeDefined())
  })

  it('logout drops favorites and reloads the cart as a guest', async () => {
    let signedIn = true
    const { wrapper, queryClient, client } = setup(
      {
        'GET /api/cart/': () => json(200, signedIn ? cartWith(item('v1', 4)) : EMPTY_CART),
        'GET /api/cart/favorites/': () => json(200, { items: ['p1'] }),
        'POST /api/auth/logout/': () => {
          signedIn = false
          return new Response(null, { status: 204 })
        },
      },
      { signedIn: true },
    )
    client.tokens.set({ access: 'a1', refresh: 'r1' })
    const { result } = renderHook(
      () => ({ cart: useCart(), favorites: useFavorites(), logout: useLogout() }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.favorites.data?.items).toEqual(['p1']))
    await waitFor(() => expect(result.current.cart.data?.items_count).toBe(4))
    await act(() => result.current.logout.mutateAsync())
    expect(queryClient.getQueryData(queryKeys.favorites)).toBeUndefined()
    await waitFor(() => expect(result.current.cart.data?.items_count).toBe(0))
  })
})

describe('favorites hooks', () => {
  it('is idle for guests', () => {
    const { wrapper, server } = setup({})
    const { result } = renderHook(() => useFavorites(), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
    expect(server.calls).toHaveLength(0)
  })

  it('toggles optimistically and rolls back on failure', async () => {
    let failAdd = false
    const { wrapper, queryClient, server } = setup(
      {
        'GET /api/cart/favorites/': () => json(200, { items: ['p1'] }),
        'POST /api/cart/favorites/': (req) =>
          failAdd
            ? json(409, errorBody('FAVORITES_FULL'))
            : json(200, { items: [(req.body as { product_id: string }).product_id, 'p1'] }),
        'DELETE /api/cart/favorites/p1/': () => new Response(null, { status: 204 }),
      },
      { signedIn: true },
    )
    const { result } = renderHook(() => ({ list: useFavorites(), toggle: useToggleFavorite() }), {
      wrapper,
    })
    await waitFor(() => expect(result.current.list.data?.items).toEqual(['p1']))

    await act(() => result.current.toggle.mutateAsync({ productId: 'p2', favorite: true }))
    await waitFor(() => expect(result.current.list.data?.items).toEqual(['p2', 'p1']))
    expect(server.callsTo('POST', '/api/cart/favorites/')[0]!.body).toEqual({ product_id: 'p2' })

    await act(() => result.current.toggle.mutateAsync({ productId: 'p1', favorite: false }))
    await waitFor(() => expect(result.current.list.data?.items).toEqual(['p2']))

    failAdd = true
    await act(() =>
      result.current.toggle.mutateAsync({ productId: 'p3', favorite: true }).catch(() => undefined),
    )
    expect(queryClient.getQueryData(queryKeys.favorites)).toEqual({ items: ['p2'] })
  })
})
