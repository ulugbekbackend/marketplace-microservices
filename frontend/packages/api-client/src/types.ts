/**
 * API contract types, aliased from the generated OpenAPI schemas.
 *
 * `pnpm gen-api` writes `src/generated/<service>.ts` from `openapi/<service>.json`. App code
 * imports only the names below, so a schema change surfaces as a compile error here or at the
 * use site instead of a silent runtime mismatch.
 */
import type { components as AuthComponents } from './generated/auth'
import type {
  components as CatalogComponents,
  operations as CatalogOperations,
} from './generated/catalog'

type AuthSchemas = AuthComponents['schemas']
type CatalogSchemas = CatalogComponents['schemas']

/* ------------------------------------------------------------------ shared */

/** UUID string. */
export type Uuid = string
/** Integer amount of tiyin (1 so'm = 100 tiyin). */
export type Tiyin = number
/** ISO 8601 UTC timestamp. */
export type IsoDateTime = string

/** The shared list envelope; every `Paginated*List` schema has this shape. */
export type Paginated<T> = {
  items: T[]
  total: number
  page: number
  page_size: number
}

/** The shared error shape: `{"error": {"code", "message", "details"}}`. */
export type ErrorBody = AuthSchemas['Error']

/* -------------------------------------------------------------------- auth */

export type User = AuthSchemas['User']
export type UserRole = AuthSchemas['RoleEnum']

export type OtpSendRequest = AuthSchemas['OtpSendRequest']
export type OtpVerifyRequest = AuthSchemas['OtpVerifyRequest']
export type OtpVerifyResponse = AuthSchemas['Login']
export type TokenRefreshRequest = AuthSchemas['RefreshRequest']
export type TokenRefreshResponse = AuthSchemas['TokenPair']
export type LogoutRequest = AuthSchemas['RefreshRequest']
export type UserUpdateRequest = AuthSchemas['PatchedUserUpdateRequest']

/** Error codes returned by the OTP endpoints (codes are not part of the OpenAPI schema). */
export type AuthErrorCode =
  'OTP_INVALID' | 'OTP_EXPIRED' | 'OTP_BLOCKED' | 'OTP_RATE_LIMITED' | 'INVALID_PHONE'

/* ----------------------------------------------------------------- catalog */

export type Category = CatalogSchemas['CategoryNode']
export type CategoryRef = CatalogSchemas['CategoryRef']
export type SellerRef = CatalogSchemas['SellerCard']

export type ProductListItem = CatalogSchemas['ProductCard']
export type ProductImage = CatalogSchemas['Image']
export type VariantAttribute = CatalogSchemas['VariantAttribute']
export type ProductVariant = CatalogSchemas['PublicVariant']
export type ProductDetail = CatalogSchemas['ProductDetail']
export type ProductListParams = NonNullable<
  CatalogOperations['products_list']['parameters']['query']
>

export type Shop = CatalogSchemas['Shop']
