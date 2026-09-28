import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { createApiClient } from '../src/client'
import { ApiProvider } from '../src/hooks/context'
import { queryKeys } from '../src/hooks/keys'
import {
  useChangeSubOrderStatus,
  useSellerOrder,
  useSellerOrders,
  useSellerOrderStats,
} from '../src/hooks/sellerOrders'
import { TokenStore } from '../src/tokens'
import type { SellerStats, SellerSubOrderDetail } from '../src/types'
import { errorBody, fakeFetch, json, memoryStorage, type Handler } from './fakeServer'

const detail: SellerSubOrderDetail = {
  id: 's1',
  order_id: 'o1',
  status: 'NEW',
  subtotal_tiyin: 50_000_000,
  commission_tiyin: 5_000_000,
  net_tiyin: 45_000_000,
  items_count: 1,
  created_at: '2026-09-27T10:00:00Z',
  updated_at: '2026-09-27T10:00:00Z',
  customer_name: 'Aziza',
  city: 'Toshkent',
  commission_rate: '0.1000',
  tracking_number: '',
  cancel_reason: '',
  items: [],
  delivery_address: {
    full_name: 'Aziza',
    phone: '+998901112233',
    region: 'Toshkent shahri',
    city: 'Toshkent',
    street: 'Navoiy 1',
    notes: '',
  },
  order_status: 'PAID',
  history: [],
}

const period = { orders: 0, gross_tiyin: 0, net_tiyin: 0 }
const stats: SellerStats = {
  today: period,
  week: period,
  month: period,
  daily: [],
  by_status: { NEW: 2, ACCEPTED: 0, SHIPPED: 0, DELIVERED: 0, CANCELLED_BY_SELLER: 0 },
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
  return { server, queryClient, wrapper }
}

describe('seller order hooks', () => {
  it('sends statuses as one comma separated value with dates and page', async () => {
    const { wrapper, server } = setup({
      'GET /api/orders/seller/': () => json(200, { items: [], total: 0, page: 1, page_size: 20 }),
    })
    const { result } = renderHook(
      () =>
        useSellerOrders({
          status: ['NEW', 'ACCEPTED'],
          date_from: '2026-09-01',
          date_to: '2026-09-27',
          page: 2,
          page_size: 20,
        }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const url = server.callsTo('GET', '/api/orders/seller/')[0]!.url
    expect(Object.fromEntries(url.searchParams)).toEqual({
      status: 'NEW,ACCEPTED',
      date_from: '2026-09-01',
      date_to: '2026-09-27',
      page: '2',
      page_size: '20',
    })
  })

  it('omits an empty status filter', async () => {
    const { wrapper, server } = setup({
      'GET /api/orders/seller/': () => json(200, { items: [], total: 0, page: 1, page_size: 20 }),
    })
    const { result } = renderHook(() => useSellerOrders({ status: [], page: 1 }), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(server.callsTo('GET', '/api/orders/seller/')[0]!.url.searchParams.has('status')).toBe(
      false,
    )
  })

  it('stores the changed detail and refetches lists and stats', async () => {
    const { wrapper, server, queryClient } = setup({
      'GET /api/orders/seller/s1/': () => json(200, detail),
      'GET /api/orders/seller/stats/': () => json(200, stats),
      'PATCH /api/orders/seller/s1/status/': () => json(200, { ...detail, status: 'ACCEPTED' }),
    })
    const { result } = renderHook(
      () => ({
        detail: useSellerOrder('s1'),
        stats: useSellerOrderStats(),
        change: useChangeSubOrderStatus(),
      }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.stats.isSuccess).toBe(true))
    await act(() =>
      result.current.change.mutateAsync({ subOrderId: 's1', body: { status: 'ACCEPTED' } }),
    )
    expect(server.callsTo('PATCH', '/api/orders/seller/s1/status/')[0]!.body).toEqual({
      status: 'ACCEPTED',
    })
    expect(
      queryClient.getQueryData<SellerSubOrderDetail>(queryKeys.sellerOrder('s1'))?.status,
    ).toBe('ACCEPTED')
    await waitFor(() => expect(server.callsTo('GET', '/api/orders/seller/stats/')).toHaveLength(2))
  })

  it('refetches the detail when someone else changed the status (409)', async () => {
    let current = detail
    const { wrapper, server } = setup({
      'GET /api/orders/seller/s1/': () => json(200, current),
      'PATCH /api/orders/seller/s1/status/': () => {
        current = { ...detail, status: 'CANCELLED_BY_SELLER' }
        return json(409, errorBody('INVALID_TRANSITION', 'x', { from: 'CANCELLED_BY_SELLER' }))
      },
    })
    const { result } = renderHook(
      () => ({ detail: useSellerOrder('s1'), change: useChangeSubOrderStatus() }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.detail.isSuccess).toBe(true))
    await act(async () => {
      await result.current.change
        .mutateAsync({ subOrderId: 's1', body: { status: 'ACCEPTED' } })
        .catch(() => undefined)
    })
    await waitFor(() => expect(result.current.change.error?.code).toBe('INVALID_TRANSITION'))
    await waitFor(() => expect(result.current.detail.data?.status).toBe('CANCELLED_BY_SELLER'))
    expect(server.callsTo('GET', '/api/orders/seller/s1/')).toHaveLength(2)
  })
})
