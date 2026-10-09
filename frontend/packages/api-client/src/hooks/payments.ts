import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ApiError } from '../errors'
import type {
  MockPaymentResult,
  Paginated,
  PaymentInitResponse,
  PaymentProvider,
  SellerPayout,
  SellerPayoutListParams,
  Uuid,
} from '../types'
import { useApi } from './context'
import { queryKeys } from './keys'

/** Asks where to pay; the caller sends the browser to `redirect_url`. */
export function useInitPayment() {
  const { payments } = useApi()
  return useMutation<PaymentInitResponse, ApiError, { orderId: Uuid; provider: PaymentProvider }>({
    mutationFn: ({ orderId, provider }) => payments.init(orderId, provider),
  })
}

/**
 * Dev only. The order turns PAID a moment later, when payment.paid reaches the order service,
 * so the order caches are dropped and the result page polls for the new status.
 */
export function useMockPayment() {
  const { payments } = useApi()
  const queryClient = useQueryClient()
  return useMutation<MockPaymentResult, ApiError, { orderId: Uuid }>({
    mutationFn: ({ orderId }) => payments.payMock(orderId),
    onSuccess: (_result, { orderId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.order(orderId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.orderStatus(orderId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.cart })
    },
  })
}

export function useSellerPayouts(params: SellerPayoutListParams) {
  const { payments } = useApi()
  return useQuery<Paginated<SellerPayout>, ApiError>({
    queryKey: queryKeys.sellerPayoutList(params),
    queryFn: ({ signal }) => payments.sellerPayouts(params, signal),
    placeholderData: keepPreviousData,
  })
}
