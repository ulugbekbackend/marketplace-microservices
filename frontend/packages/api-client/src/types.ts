/**
 * API contract types.
 *
 * Hand-written to match the service contracts until the OpenAPI schemas are published.
 * `pnpm gen-api` writes `src/generated/<service>.ts` from `openapi/<service>.json`; once a
 * service's schema exists, replace the matching block below with aliases to the generated
 * schema, e.g.
 *
 *   import type { components } from './generated/catalog'
 *   export type ProductListItem = components['schemas']['ProductListItem']
 *
 * Consumers import only these names, so swapping the source does not touch app code.
 */

/* ------------------------------------------------------------------ shared */

/** UUID string. */
export type Uuid = string
/** Integer amount of tiyin (1 so'm = 100 tiyin). */
export type Tiyin = number
/** ISO 8601 UTC timestamp. */
export type IsoDateTime = string

export type Paginated<T> = {
  items: T[]
  total: number
  page: number
  page_size: number
}

export type ErrorBody = {
  error: {
    code: string
    message: string
    details?: unknown
  }
}

/* -------------------------------------------------------------------- auth */

export type UserRole = 'customer' | 'seller' | 'admin'

export type User = {
  id: Uuid
  phone: string
  full_name: string
  role: UserRole
}

export type OtpSendRequest = { phone: string }
export type OtpVerifyRequest = { phone: string; code: string }
export type OtpVerifyResponse = { access: string; refresh: string; user: User }
export type TokenRefreshRequest = { refresh: string }
export type TokenRefreshResponse = { access: string; refresh: string }
export type LogoutRequest = { refresh: string }
export type UserUpdateRequest = { full_name: string }

/** Error codes returned by the OTP endpoints. */
export type AuthErrorCode =
  'OTP_INVALID' | 'OTP_EXPIRED' | 'OTP_BLOCKED' | 'OTP_RATE_LIMITED' | 'INVALID_PHONE'

/* ----------------------------------------------------------------- catalog */

export type Category = {
  id: Uuid
  name: string
  slug: string
  children: Category[]
}

export type CategoryRef = {
  id: Uuid
  name: string
  slug: string
}

export type SellerRef = {
  id: Uuid
  shop_name: string
  slug: string
}

export type ProductListItem = {
  id: Uuid
  title: string
  slug: string
  min_price_tiyin: Tiyin
  max_price_tiyin: Tiyin
  in_stock: boolean
  image_url: string | null
  seller: SellerRef
}

export type ProductImage = {
  id: Uuid
  thumb_url: string
  medium_url: string
  large_url: string
  position: number
}

export type VariantAttribute = {
  code: string
  name: string
  value: string
}

export type ProductVariant = {
  id: Uuid
  sku: string
  price_tiyin: Tiyin
  available: number
  in_stock: boolean
  attributes: VariantAttribute[]
}

export type ProductDetail = {
  id: Uuid
  title: string
  slug: string
  description: string
  category: CategoryRef
  seller: SellerRef
  images: ProductImage[]
  variants: ProductVariant[]
  min_price_tiyin: Tiyin
  max_price_tiyin: Tiyin
  in_stock: boolean
}

export type ProductListParams = {
  category?: string
  seller?: string
  page?: number
  page_size?: number
}

export type Shop = {
  id: Uuid
  shop_name: string
  slug: string
  product_count: number
  created_at: IsoDateTime
}
