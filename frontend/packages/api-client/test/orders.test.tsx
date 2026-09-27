import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApiClient } from '../src/client'
import { ApiError, CLIENT_ERROR } from '../src/errors'
import { useCart } from '../src/hooks/cart'
import { ApiProvider } from '../src/hooks/context'
import { queryKeys } from '../src/hooks/keys'
import {
  isRetryableCheckoutError,
  ORDER_POLL_INTERVAL_MS,
  orderPollInterval,
  useCancelOrder,
  useCheckout,
  useMockPay,
  useOrder,
  useOrderStatus,
} from '../src/hooks/orders'
import { IDEMPOTENCY_HEADER } from '../src/idempotency'
import { REFRESH_TOKEN_KEY, TokenStore } from '../src/tokens'
import type { Order, OrderStatus } from '../src/types'
import { errorBody, fakeFetch, json, memoryStorage, type Handler } from './fakeServer'

const address = {
  full_name: 'Aziza Karimova',
  phone: '+998901112233',
  region: 'Toshkent shahri',
  city: 'Toshkent',
  street: 'Navoiy 12',
  notes: '',
}

const order = (status: OrderStatus, reservedUntil: string | null = null): Order => ({
  id: 'o1',
  status,
  reserved_until: reservedUntil,
  total_tiyin: 100_000_00,
  cancel_reason: '',
  created_at: '2026-09-27T10:00:00Z',
  updated_at: '2026-09-27T10:00:00Z',
  delivery_address: address,
  history: [],
  sellers: [],
})

function setup(routes: Record<string, Handler>) {
  const server = fakeFetch(routes)
  const tokens = new TokenStore(memoryStorage({ [REFRESH_TOKEN_KEY]: 'r1' }))
  tokens.set({ access: 'a1', refresh: 'r1' })
  const client = createApiClient({ baseUrl: 'http://api.test', tokens, fetch: server.fetch })
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

afterEach(() => vi.useRealTimers())

describe('orderPollInterval', () => {
  const now = Date.parse('2026-09-27T10:00:00Z')
  it('polls while pending or reserved past the deadline, otherwise stops', () => {
    expect(orderPollInterval(undefined, now)).toBe(false)
    expect(orderPollInterval({ status: 'PENDING', reserved_until: null }, now)).toBe(
      ORDER_POLL_INTERVAL_MS,
    )
    expect(
      orderPollInterval({ status: 'RESERVED', reserved_until: '2026-09-27T10:05:00Z' }, now),
    ).toBe(false)
    expect(
      orderPollInterval({ status: 'RESERVED', reserved_until: '2026-09-27T09:59:59Z' }, now),
    ).toBe(ORDER_POLL_INTERVAL_MS)
    for (const status of ['PAID', 'EXPIRED', 'CANCELLED', 'COMPLETED'] as const) {
      expect(orderPollInterval({ status, reserved_until: null }, now)).toBe(false)
    }
  })

  it('retries only failures that a same-key retry can fix', () => {
    expect(isRetryableCheckoutError(new ApiError(0, CLIENT_ERROR.NETWORK, 'x'))).toBe(true)
    expect(isRetryableCheckoutError(new ApiError(409, 'IDEMPOTENCY_IN_PROGRESS', 'x'))).toBe(true)
    expect(isRetryableCheckoutError(new ApiError(503, 'SERVICE_UNAVAILABLE', 'x'))).toBe(true)
    expect(isRetryableCheckoutError(new ApiError(409, 'ITEMS_UNAVAILABLE', 'x'))).toBe(false)
    expect(isRetryableCheckoutError(new ApiError(409, 'IDEMPOTENCY_KEY_REUSED', 'x'))).toBe(false)
  })
})

describe('useCheckout', () => {
  it('sends the idempotency key and reuses it for automatic retries', async () => {
    let attempts = 0
    const { server, wrapper } = setup({
      'POST /api/orders/checkout/': () =>
        ++attempts === 1
          ? json(409, errorBody('IDEMPOTENCY_IN_PROGRESS'))
          : json(202, { order_id: 'o1', status: 'RESERVED' }),
    })
    const { result } = renderHook(() => useCheckout(), { wrapper })
    const data = await act(() => result.current.mutateAsync({ address, idempotencyKey: 'key-1' }))
    expect(data).toEqual({ order_id: 'o1', status: 'RESERVED' })
    const calls = server.callsTo('POST', '/api/orders/checkout/')
    expect(calls).toHaveLength(2)
    expect(calls.map((c) => c.headers[IDEMPOTENCY_HEADER])).toEqual(['key-1', 'key-1'])
    expect(calls[0]!.body).toEqual({ address })
  })

  it('does not retry unavailable items and refetches the cart', async () => {
    let cartReads = 0
    const { server, wrapper } = setup({
      'GET /api/cart/': () => {
        cartReads += 1
        return json(200, {
          groups: [],
          total_tiyin: 0,
          items_count: 0,
          has_unavailable: false,
          has_price_changes: false,
          removed: [],
        })
      },
      'POST /api/orders/checkout/': () =>
        json(
          409,
          errorBody('ITEMS_UNAVAILABLE', 'x', {
            items: [{ variant_id: 'v1', reason: 'out_of_stock', available: 0 }],
          }),
        ),
    })
    const { result } = renderHook(() => ({ cart: useCart(), checkout: useCheckout() }), {
      wrapper,
    })
    await waitFor(() => expect(cartReads).toBe(1))
    const error = await act(() =>
      result.current.checkout
        .mutateAsync({ address, idempotencyKey: 'key-2' })
        .catch((e: unknown) => e),
    )
    expect((error as ApiError).code).toBe('ITEMS_UNAVAILABLE')
    expect(server.callsTo('POST', '/api/orders/checkout/')).toHaveLength(1)
    await waitFor(() => expect(cartReads).toBe(2))
  })
})

describe('useOrderStatus', () => {
  it('polls every 2 s while pending, stops at a stable status and refreshes the detail', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const statuses: OrderStatus[] = ['PENDING', 'PENDING', 'RESERVED']
    let statusCalls = 0
    let detailCalls = 0
    const { wrapper } = setup({
      'GET /api/orders/o1/status/': () => {
        const status = statuses[Math.min(statusCalls, statuses.length - 1)]!
        statusCalls += 1
        return json(200, {
          status,
          reserved_until: status === 'RESERVED' ? '2099-01-01T00:00:00Z' : null,
        })
      },
      'GET /api/orders/o1/': () => {
        detailCalls += 1
        return json(
          200,
          detailCalls === 1 ? order('PENDING') : order('RESERVED', '2099-01-01T00:00:00Z'),
        )
      },
    })
    const { result } = renderHook(
      () => ({ detail: useOrder('o1'), status: useOrderStatus('o1') }),
      {
        wrapper,
      },
    )
    await waitFor(() => expect(result.current.detail.data?.status).toBe('PENDING'))
    await waitFor(() => expect(statusCalls).toBe(1))
    await act(() => vi.advanceTimersByTimeAsync(ORDER_POLL_INTERVAL_MS))
    await waitFor(() => expect(statusCalls).toBe(2))
    await act(() => vi.advanceTimersByTimeAsync(ORDER_POLL_INTERVAL_MS))
    await waitFor(() => expect(statusCalls).toBe(3))
    // RESERVED with a future deadline: the detail is refreshed and polling stops
    await waitFor(() => expect(result.current.detail.data?.status).toBe('RESERVED'))
    await act(() => vi.advanceTimersByTimeAsync(ORDER_POLL_INTERVAL_MS * 5))
    expect(statusCalls).toBe(3)
  })
})

describe('order actions', () => {
  it('mock pay stores the paid order and refetches the cart; cancel stores its detail', async () => {
    let cartReads = 0
    const { queryClient, wrapper } = setup({
      'GET /api/cart/': () => {
        cartReads += 1
        return json(200, {
          groups: [],
          total_tiyin: 0,
          items_count: 0,
          has_unavailable: false,
          has_price_changes: false,
          removed: [],
        })
      },
      'POST /api/orders/o1/pay/mock/': () => json(200, order('PAID')),
      'POST /api/orders/o2/cancel/': () => json(200, { ...order('CANCELLED'), id: 'o2' }),
    })
    const { result } = renderHook(
      () => ({ cart: useCart(), pay: useMockPay(), cancel: useCancelOrder() }),
      { wrapper },
    )
    await waitFor(() => expect(cartReads).toBe(1))
    await act(() => result.current.pay.mutateAsync({ orderId: 'o1' }))
    expect(queryClient.getQueryData<Order>(queryKeys.order('o1'))?.status).toBe('PAID')
    expect(queryClient.getQueryData(queryKeys.orderStatus('o1'))).toEqual({
      status: 'PAID',
      reserved_until: null,
    })
    await waitFor(() => expect(cartReads).toBe(2))

    await act(() => result.current.cancel.mutateAsync({ orderId: 'o2' }))
    expect(queryClient.getQueryData<Order>(queryKeys.order('o2'))?.status).toBe('CANCELLED')
  })
})
