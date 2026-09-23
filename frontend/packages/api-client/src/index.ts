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
export { authEndpoints, catalogEndpoints } from './endpoints'
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
export { ApiProvider, useApi, useSession } from './hooks/context'
export { queryKeys } from './hooks/keys'
