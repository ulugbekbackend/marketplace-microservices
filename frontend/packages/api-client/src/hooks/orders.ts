import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'
import { CLIENT_ERROR, isApiError, type ApiError } from '../errors'
import type {
  CheckoutResult,
  DeliveryAddress,
  Order,
  OrderErrorCode,
  OrderListParams,
  OrderStatusInfo,
  Paginated,
  OrderSummary,
  Uuid,
} from '../types'
import { useApi } from './context'
import { queryKeys } from './keys'

/** How often the order status is polled while the order is still settling. */
export const ORDER_POLL_INTERVAL_MS = 2000

/** Automatic retries of one checkout submit (same idempotency key). */
const CHECKOUT_RETRIES = 2

/**
 * Next poll delay for an order status, or `false` to stop. Polling runs while the order is
 * PENDING, and while it is RESERVED past its deadline (the server expires it lazily, so the
 * status flips to EXPIRED on a later read). Every other status is stable or terminal.
 */
export function orderPollInterval(
  info: OrderStatusInfo | undefined,
  now: number = Date.now(),
): number | false {
  if (!info) return false
  if (info.status === 'PENDING') return ORDER_POLL_INTERVAL_MS
  if (
    info.status === 'RESERVED' &&
    info.reserved_until !== null &&
    Date.parse(info.reserved_until) <= now
  ) {
    return ORDER_POLL_INTERVAL_MS
  }
  return false
}

const hasCode = (error: unknown, codes: readonly OrderErrorCode[]) =>
  isApiError(error) && (codes as readonly string[]).includes(error.code)

/**
 * Failures worth retrying with the same key: the request may not have reached the server, the
 * first attempt is still running, or a dependency was briefly down. The server stores only
 * successful checkouts, so a retry either replays that success or runs the checkout again.
 */
export function isRetryableCheckoutError(error: unknown): boolean {
  if (!isApiError(error)) return false
  if (error.code === CLIENT_ERROR.NETWORK) return true
  return hasCode(error, ['IDEMPOTENCY_IN_PROGRESS', 'SERVICE_UNAVAILABLE'])
}

/** Writes a fresh order detail into the detail and status caches; the list is refetched. */
function storeOrder(queryClient: QueryClient, order: Order) {
  queryClient.setQueryData(queryKeys.order(order.id), order)
  queryClient.setQueryData<OrderStatusInfo>(queryKeys.orderStatus(order.id), {
    status: order.status,
    reserved_until: order.reserved_until,
  })
  void queryClient.invalidateQueries({ queryKey: [...queryKeys.orders, 'list'] })
}

/** The order changed under us (expired, paid elsewhere): reload everything about it. */
function refreshOrder(queryClient: QueryClient, orderId: Uuid) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.order(orderId) })
  void queryClient.invalidateQueries({ queryKey: queryKeys.orderStatus(orderId) })
  void queryClient.invalidateQueries({ queryKey: [...queryKeys.orders, 'list'] })
}

export type CheckoutVars = {
  address: DeliveryAddress
  /** One key per checkout attempt, reused for every retry of it (see `newIdempotencyKey`). */
  idempotencyKey: string
}

export function useCheckout() {
  const { orders } = useApi()
  const queryClient = useQueryClient()
  return useMutation<CheckoutResult, ApiError, CheckoutVars>({
    mutationFn: ({ address, idempotencyKey }) => orders.checkout({ address }, idempotencyKey),
    retry: (failureCount, error) =>
      failureCount < CHECKOUT_RETRIES && isRetryableCheckoutError(error),
    retryDelay: (attempt) => 500 * 2 ** attempt,
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: [...queryKeys.orders, 'list'] }),
    onError: (error) => {
      // The cart changed (emptied, stock gone): show the current one.
      if (hasCode(error, ['CART_EMPTY', 'ITEMS_UNAVAILABLE'])) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.cart })
      }
    },
  })
}

export function useOrder(orderId: Uuid | undefined) {
  const { orders } = useApi()
  return useQuery<Order, ApiError>({
    queryKey: queryKeys.order(orderId ?? ''),
    queryFn: ({ signal }) => orders.detail(orderId!, signal),
    enabled: Boolean(orderId),
  })
}

/**
 * Polls the lightweight status endpoint (see `orderPollInterval`). When the status differs from
 * the cached detail, the detail and the list are refetched.
 */
export function useOrderStatus(orderId: Uuid | undefined, options: { enabled?: boolean } = {}) {
  const { orders } = useApi()
  const queryClient = useQueryClient()
  return useQuery<OrderStatusInfo, ApiError>({
    queryKey: queryKeys.orderStatus(orderId ?? ''),
    queryFn: async ({ signal }) => {
      const info = await orders.status(orderId!, signal)
      const detail = queryClient.getQueryData<Order>(queryKeys.order(orderId!))
      if (
        detail &&
        (detail.status !== info.status || detail.reserved_until !== info.reserved_until)
      ) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.order(orderId!) })
        void queryClient.invalidateQueries({ queryKey: [...queryKeys.orders, 'list'] })
      }
      return info
    },
    enabled: Boolean(orderId) && (options.enabled ?? true),
    staleTime: 0,
    refetchInterval: (query) => orderPollInterval(query.state.data),
  })
}

export function useOrders(params: OrderListParams) {
  const { orders } = useApi()
  return useQuery<Paginated<OrderSummary>, ApiError>({
    queryKey: queryKeys.orderList(params),
    queryFn: ({ signal }) => orders.list(params, signal),
    placeholderData: keepPreviousData,
  })
}

/** Cancels while PENDING or RESERVED; the returned detail replaces the cache. */
export function useCancelOrder() {
  const { orders } = useApi()
  const queryClient = useQueryClient()
  return useMutation<Order, ApiError, { orderId: Uuid }>({
    mutationFn: ({ orderId }) => orders.cancel(orderId),
    onSuccess: (order) => storeOrder(queryClient, order),
    onError: (_error, { orderId }) => refreshOrder(queryClient, orderId),
  })
}

/** Dev-only mock payment. The server clears the cart once the order is paid. */
export function useMockPay() {
  const { orders } = useApi()
  const queryClient = useQueryClient()
  return useMutation<Order, ApiError, { orderId: Uuid }>({
    mutationFn: ({ orderId }) => orders.payMock(orderId),
    onSuccess: (order) => {
      storeOrder(queryClient, order)
      void queryClient.invalidateQueries({ queryKey: queryKeys.cart })
    },
    onError: (error, { orderId }) => {
      // 404 = mock payments are off: nothing about the order changed.
      if (!(isApiError(error) && error.status === 404)) refreshOrder(queryClient, orderId)
    },
  })
}
