import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'
import { isApiError, type ApiError } from '../errors'
import type {
  Paginated,
  SellerOrderListParams,
  SellerStats,
  SellerSubOrder,
  SellerSubOrderDetail,
  SubOrderStatusChangeRequest,
  Uuid,
} from '../types'
import { useApi } from './context'
import { queryKeys } from './keys'

/** The sidebar's "new orders" badge re-reads the stats this often. */
export const SELLER_STATS_POLL_INTERVAL_MS = 60_000

export function useSellerOrders(params: SellerOrderListParams) {
  const { sellerOrders } = useApi()
  return useQuery<Paginated<SellerSubOrder>, ApiError>({
    queryKey: queryKeys.sellerOrderList(params),
    queryFn: ({ signal }) => sellerOrders.list(params, signal),
    placeholderData: keepPreviousData,
  })
}

export function useSellerOrder(subOrderId: Uuid | undefined) {
  const { sellerOrders } = useApi()
  return useQuery<SellerSubOrderDetail, ApiError>({
    queryKey: queryKeys.sellerOrder(subOrderId ?? ''),
    queryFn: ({ signal }) => sellerOrders.detail(subOrderId!, signal),
    enabled: Boolean(subOrderId),
  })
}

/** Dashboard numbers and per-status counts; pass `refetchInterval` to keep a badge fresh. */
export function useSellerOrderStats(options: { refetchInterval?: number | false } = {}) {
  const { sellerOrders } = useApi()
  return useQuery<SellerStats, ApiError>({
    queryKey: queryKeys.sellerOrderStats,
    queryFn: ({ signal }) => sellerOrders.stats(signal),
    refetchInterval: options.refetchInterval ?? false,
  })
}

/** A status change moves counts and sums: refresh every list and the stats. */
export function invalidateSellerOrders(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: [...queryKeys.sellerOrders, 'list'] }),
    queryClient.invalidateQueries({ queryKey: queryKeys.sellerOrderStats }),
  ])
}

export type SubOrderStatusVars = { subOrderId: Uuid; body: SubOrderStatusChangeRequest }

/**
 * Accept, ship, deliver or cancel a sub-order. The answer replaces the cached detail; lists and
 * stats are refetched. On 404/409 (someone else changed it, or the order stopped) the detail is
 * refetched too, so the page shows the current state.
 */
export function useChangeSubOrderStatus() {
  const { sellerOrders } = useApi()
  const queryClient = useQueryClient()
  return useMutation<SellerSubOrderDetail, ApiError, SubOrderStatusVars>({
    mutationFn: ({ subOrderId, body }) => sellerOrders.setStatus(subOrderId, body),
    onSuccess: (detail) => {
      queryClient.setQueryData(queryKeys.sellerOrder(detail.id), detail)
      void invalidateSellerOrders(queryClient)
    },
    onError: (error, { subOrderId }) => {
      if (isApiError(error) && (error.status === 409 || error.status === 404)) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.sellerOrder(subOrderId) })
        void invalidateSellerOrders(queryClient)
      }
    },
  })
}
