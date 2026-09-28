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
  sellerCatalogEndpoints,
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
  useAttributes,
  useSellerApplication,
  useSellerProduct,
  useSellerProductDetails,
  useSellerProducts,
  useUpdateVariantStock,
  type StockUpdateVars,
} from './hooks/seller'
export { ApiProvider, useApi, useSession } from './hooks/context'
export { queryKeys } from './hooks/keys'
