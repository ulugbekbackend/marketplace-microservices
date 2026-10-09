export {
  buildUrl,
  createApiClient,
  DEFAULT_API_URL,
  REFRESH_PATH,
  type ApiClient,
  type ApiClientOptions,
  type HttpMethod,
  type Query,
  type RequestOptions,
} from './client'
export {
  authEndpoints,
  cartEndpoints,
  catalogEndpoints,
  orderEndpoints,
  paymentEndpoints,
  searchEndpoints,
  searchQuery,
  sellerCatalogEndpoints,
  sellerOrderEndpoints,
} from './endpoints'
export {
  AUTH_ERROR_KEYS,
  errorDetail,
  loginErrorKey,
  retryAfterSeconds,
  type LoginErrorKey,
} from './authErrors'
export { uploadWithProgress, type UploadOptions } from './upload'
export {
  ApiError,
  CLIENT_ERROR,
  isApiError,
  parseErrorResponse,
  shouldRetry,
  toApiError,
} from './errors'
export { IDEMPOTENCY_HEADER, newIdempotencyKey } from './idempotency'
export { REFRESH_TOKEN_KEY, TokenStore, type TokenSnapshot, type TokenStorage } from './tokens'
export * from './types'

export { useCategories, useProduct, useProducts, useShop } from './hooks/catalog'
export { SUGGEST_MIN_LENGTH, useSearch, useSuggest } from './hooks/search'
export { useLogout, useMe, useSendOtp, useUpdateMe, useVerifyOtp } from './hooks/auth'
export {
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
} from './hooks/cart'
export {
  isRetryableCheckoutError,
  ORDER_POLL_INTERVAL_MS,
  orderPollInterval,
  useCancelOrder,
  useCheckout,
  useMockPay,
  useOrder,
  useOrders,
  useOrderStatus,
  type CheckoutVars,
} from './hooks/orders'
export {
  APPLICATION_POLL_INTERVAL_MS,
  IMAGE_POLL_INTERVAL_MS,
  invalidateSellerLists,
  useApplySeller,
  useDeleteProductImage,
  useAttributes,
  useSellerApplication,
  useSellerProduct,
  useSellerProducts,
  useUpdateVariantStock,
  type ImageDeleteVars,
  type StockUpdateVars,
} from './hooks/seller'
export {
  invalidateSellerOrders,
  SELLER_STATS_POLL_INTERVAL_MS,
  useChangeSubOrderStatus,
  useSellerOrder,
  useSellerOrders,
  useSellerOrderStats,
  type SubOrderStatusVars,
} from './hooks/sellerOrders'
export { useInitPayment, useMockPayment, useSellerPayouts } from './hooks/payments'
export { ApiProvider, useApi, useSession } from './hooks/context'
export { queryKeys } from './hooks/keys'
