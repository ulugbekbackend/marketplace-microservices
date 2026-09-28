/**
 * API contract types, aliased from the generated OpenAPI schemas.
 *
 * `pnpm gen-api` writes `src/generated/<service>.ts` from `openapi/<service>.json`. App code
 * imports only the names below, so a schema change surfaces as a compile error here or at the
 * use site instead of a silent runtime mismatch.
 */
import type { components as AuthComponents } from './generated/auth'
import type { components as CartComponents } from './generated/cart'
import type {
  components as CatalogComponents,
  operations as CatalogOperations,
} from './generated/catalog'
import type {
  components as OrderComponents,
  operations as OrderOperations,
} from './generated/order'

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

export type SellerApplication = AuthSchemas['SellerApplication']
export type SellerApplicationStatus = AuthSchemas['StatusEnum']
export type SellerApplyRequest = AuthSchemas['SellerApplyRequest']

/** Error codes of the seller application endpoints (not part of the OpenAPI schema). */
export type SellerApplicationErrorCode = 'ALREADY_SELLER' | 'APPLICATION_PENDING' | 'NOT_FOUND'

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

/* ---------------------------------------------------------- catalog: seller */

export type ProductStatus = CatalogSchemas['ProductStatusEnum']
export type SellerProduct = CatalogSchemas['SellerProduct']
export type SellerProductDetail = CatalogSchemas['SellerProductDetail']
export type SellerVariant = CatalogSchemas['SellerVariant']
export type SellerImage = CatalogSchemas['SellerImage']
export type ImageStatus = CatalogSchemas['ImageStatusEnum']
export type ImageContentType = CatalogSchemas['ImageContentTypeEnum']
export type Attribute = CatalogSchemas['Attribute']
export type AttributeValue = CatalogSchemas['AttributeValue']
export type SellerProductListParams = NonNullable<
  CatalogOperations['seller_products_list']['parameters']['query']
>
export type ProductCreateRequest = CatalogSchemas['ProductCreateRequest']
export type ProductUpdateRequest = CatalogSchemas['PatchedProductUpdateRequest']
export type VariantCreateRequest = CatalogSchemas['VariantCreateRequest']
export type VariantUpdateRequest = CatalogSchemas['PatchedVariantUpdateRequest']
export type StockUpdateRequest = Required<CatalogSchemas['PatchedStockUpdateRequest']>
export type PresignRequest = CatalogSchemas['PresignRequestRequest']
export type PresignResponse = CatalogSchemas['PresignResponse']
export type ImageAttachRequest = CatalogSchemas['ImageAttachRequest']

/** Error codes of the seller catalog endpoints (not part of the OpenAPI schema). */
export type SellerCatalogErrorCode =
  | 'SELLER_NOT_FOUND'
  | 'SKU_TAKEN'
  | 'VARIANT_EXISTS'
  | 'STOCK_BELOW_RESERVED'
  | 'INVALID_IMAGE_KEY'
  | 'IMAGE_EXISTS'
  | 'LAST_ACTIVE_VARIANT'
  | 'VALIDATION_ERROR'

/* -------------------------------------------------------------------- cart */

type CartSchemas = CartComponents['schemas']

export type Cart = CartSchemas['CartOut']
export type CartGroup = CartSchemas['SellerGroupOut']
export type CartItem = CartSchemas['CartItemOut']
export type CartItemAttribute = CartSchemas['VariantAttribute']
export type CartAddItemRequest = CartSchemas['AddItemIn']
export type CartUpdateItemRequest = CartSchemas['UpdateItemIn']
export type FavoriteRequest = CartSchemas['FavoriteIn']
export type Favorites = CartSchemas['FavoritesOut']

/** Error codes returned by the cart service (codes are not part of the OpenAPI schema). */
export type CartErrorCode =
  | 'OUT_OF_STOCK'
  | 'VARIANT_INACTIVE'
  | 'VARIANT_NOT_FOUND'
  | 'NOT_IN_CART'
  | 'CART_FULL'
  | 'FAVORITES_FULL'
  | 'CATALOG_UNAVAILABLE'
  | 'VALIDATION_ERROR'

/* ------------------------------------------------------------------- order */

type OrderSchemas = OrderComponents['schemas']

export type OrderStatus = OrderSchemas['OrderStatusEnum']
export type SubOrderStatus = OrderSchemas['SubOrderStatusEnum']
export type DeliveryAddress = OrderSchemas['AddressRequest']
export type CheckoutRequest = OrderSchemas['CheckoutRequest']
export type CheckoutResult = OrderSchemas['CheckoutResult']
export type Order = OrderSchemas['OrderDetail']
export type OrderSellerGroup = OrderSchemas['SellerGroup']
export type OrderItem = OrderSchemas['OrderItem']
export type OrderHistoryEntry = OrderSchemas['OrderHistory']
export type OrderStatusInfo = OrderSchemas['OrderStatus']
export type OrderSummary = OrderSchemas['OrderSummary']
export type OrderListParams = NonNullable<OrderOperations['orders_list']['parameters']['query']>

/** Error codes returned by the order service (codes are not part of the OpenAPI schema). */
export type OrderErrorCode =
  | 'CART_EMPTY'
  | 'ITEMS_UNAVAILABLE'
  | 'IDEMPOTENCY_KEY_REQUIRED'
  | 'IDEMPOTENCY_KEY_INVALID'
  | 'IDEMPOTENCY_KEY_REUSED'
  | 'IDEMPOTENCY_IN_PROGRESS'
  | 'INVALID_TRANSITION'
  | 'ORDER_EXPIRED'
  | 'NOT_RESERVED'
  | 'SERVICE_UNAVAILABLE'
  | 'VALIDATION_ERROR'

/** One entry of `details.items` in an `ITEMS_UNAVAILABLE` error. */
export type UnavailableItem = {
  variant_id: Uuid
  reason: 'not_found' | 'inactive' | 'out_of_stock'
  available: number
}

/* ----------------------------------------------------------- order: seller */

export type SellerSubOrder = OrderSchemas['SellerSubOrder']
export type SellerSubOrderDetail = OrderSchemas['SellerSubOrderDetail']
export type SellerOrderItem = OrderSchemas['SellerItem']
export type SubOrderHistoryEntry = OrderSchemas['SubOrderHistory']
export type SubOrderTargetStatus = OrderSchemas['SubOrderTargetStatusEnum']
export type SubOrderStatusChangeRequest = OrderSchemas['PatchedSubOrderStatusChangeRequest'] & {
  status: SubOrderTargetStatus
}
export type SellerStats = OrderSchemas['SellerStats']
export type SellerPeriodStats = OrderSchemas['PeriodStats']
export type SellerDailyStats = OrderSchemas['DailyStats']
export type SubOrderStatusCounts = OrderSchemas['StatusCounts']
/** `status` is sent as one comma separated value (the server also accepts repeats). */
export type SellerOrderListParams = NonNullable<
  OrderOperations['seller_orders_list']['parameters']['query']
>

/** Error codes of the seller order endpoints (not part of the OpenAPI schema). */
export type SellerOrderErrorCode =
  'INVALID_TRANSITION' | 'ORDER_NOT_ACTIVE' | 'VALIDATION_ERROR' | 'NOT_FOUND'
