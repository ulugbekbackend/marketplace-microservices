import type { ApiClient, Query } from './client'
import type {
  Attribute,
  Cart,
  CartAddItemRequest,
  CartUpdateItemRequest,
  Category,
  CheckoutRequest,
  CheckoutResult,
  Favorites,
  ImageAttachRequest,
  Order,
  OrderListParams,
  OrderStatusInfo,
  OrderSummary,
  OtpVerifyResponse,
  Paginated,
  PresignRequest,
  PresignResponse,
  ProductCreateRequest,
  ProductDetail,
  ProductListItem,
  ProductListParams,
  ProductUpdateRequest,
  SearchParams,
  SearchResponse,
  SellerApplication,
  SellerApplyRequest,
  SellerOrderListParams,
  SellerStats,
  SellerSubOrder,
  SellerSubOrderDetail,
  SellerImage,
  SellerProduct,
  SellerProductDetail,
  SellerProductListParams,
  SellerVariant,
  Shop,
  StockUpdateRequest,
  SubOrderStatusChangeRequest,
  SuggestResponse,
  User,
  UserUpdateRequest,
  Uuid,
  VariantCreateRequest,
  VariantUpdateRequest,
} from './types'

const seg = (value: string) => encodeURIComponent(value)

export function authEndpoints(client: ApiClient) {
  return {
    sendOtp: (phone: string) => client.post<void>('/api/auth/otp/send/', { phone }),

    /** Verifies the code and stores the issued tokens. */
    verifyOtp: async (phone: string, code: string) => {
      const data = await client.post<OtpVerifyResponse>('/api/auth/otp/verify/', { phone, code })
      client.tokens.set({ access: data.access, refresh: data.refresh })
      return data
    },

    /** Revokes the refresh token server-side (best effort) and always clears local tokens. */
    logout: async () => {
      const refresh = client.tokens.getRefresh()
      try {
        if (refresh) await client.post<void>('/api/auth/logout/', { refresh })
      } finally {
        client.tokens.clear()
      }
    },

    me: (signal?: AbortSignal) => client.get<User>('/api/auth/me/', { signal }),

    updateMe: (body: UserUpdateRequest) => client.patch<User>('/api/auth/me/', body),

    /** The caller's latest seller application; 404 `NOT_FOUND` when there is none yet. */
    sellerApplication: (signal?: AbortSignal) =>
      client.get<SellerApplication>('/api/auth/seller/application/', { signal }),

    /** 409 `APPLICATION_PENDING` while one waits for review, `ALREADY_SELLER` for sellers. */
    applySeller: (body: SellerApplyRequest) =>
      client.post<SellerApplication>('/api/auth/seller/apply/', body),
  }
}

/** The seller cabinet side of the catalog: the caller's own products, variants and images. */
export function sellerCatalogEndpoints(client: ApiClient) {
  const base = '/api/catalog/seller'
  return {
    products: (params: SellerProductListParams = {}, signal?: AbortSignal) =>
      client.get<Paginated<SellerProduct>>(`${base}/products/`, { query: params, signal }),

    product: (productId: Uuid, signal?: AbortSignal) =>
      client.get<SellerProductDetail>(`${base}/products/${seg(productId)}/`, { signal }),

    createProduct: (body: ProductCreateRequest) =>
      client.post<SellerProductDetail>(`${base}/products/`, body),

    updateProduct: (productId: Uuid, body: ProductUpdateRequest) =>
      client.patch<SellerProductDetail>(`${base}/products/${seg(productId)}/`, body),

    /** Soft delete: the product becomes archived. */
    archiveProduct: (productId: Uuid) => client.delete<void>(`${base}/products/${seg(productId)}/`),

    createVariant: (productId: Uuid, body: VariantCreateRequest) =>
      client.post<SellerVariant>(`${base}/products/${seg(productId)}/variants/`, body),

    updateVariant: (variantId: Uuid, body: VariantUpdateRequest) =>
      client.patch<SellerVariant>(`${base}/variants/${seg(variantId)}/`, body),

    /** 409 `STOCK_BELOW_RESERVED` with `details.reserved` when orders hold more units. */
    setStock: (variantId: Uuid, body: StockUpdateRequest) =>
      client.patch<SellerVariant>(`${base}/variants/${seg(variantId)}/stock/`, body),

    presignUpload: (body: PresignRequest) =>
      client.post<PresignResponse>(`${base}/uploads/presign/`, body),

    /** Registers an uploaded original; the image starts `processing`. */
    attachImage: (productId: Uuid, body: ImageAttachRequest) =>
      client.post<SellerImage>(`${base}/products/${seg(productId)}/images/`, body),

    /** 204; the remaining images are renumbered from 0. */
    deleteImage: (productId: Uuid, imageId: Uuid) =>
      client.delete<void>(`${base}/products/${seg(productId)}/images/${seg(imageId)}/`),

    attributes: (signal?: AbortSignal) =>
      client.get<Attribute[]>('/api/catalog/attributes/', { signal }),
  }
}

export function catalogEndpoints(client: ApiClient) {
  return {
    categories: (signal?: AbortSignal) =>
      client.get<Category[]>('/api/catalog/categories/', { signal }),

    products: (params: ProductListParams = {}, signal?: AbortSignal) =>
      client.get<Paginated<ProductListItem>>('/api/catalog/products/', { query: params, signal }),

    product: (slug: string, signal?: AbortSignal) =>
      client.get<ProductDetail>(`/api/catalog/products/${seg(slug)}/`, { signal }),

    shop: (slug: string, signal?: AbortSignal) =>
      client.get<Shop>(`/api/catalog/shops/${seg(slug)}/`, { signal }),
  }
}

/**
 * Cart and favorites. Guests are identified by an httpOnly `guest_id` cookie that the cart
 * service sets on the API host, so every call sends credentials.
 */
export function cartEndpoints(client: ApiClient) {
  const withCookie = { credentials: 'include' } as const
  return {
    get: (signal?: AbortSignal) => client.get<Cart>('/api/cart/', { ...withCookie, signal }),

    /** Adds units to the line (the server caps a line at 99). */
    addItem: (body: CartAddItemRequest) => client.post<Cart>('/api/cart/items/', body, withCookie),

    /** Sets the quantity; 0 removes the line. */
    updateItem: (variantId: Uuid, body: CartUpdateItemRequest) =>
      client.patch<Cart>(`/api/cart/items/${seg(variantId)}/`, body, withCookie),

    removeItem: (variantId: Uuid) =>
      client.delete<Cart>(`/api/cart/items/${seg(variantId)}/`, withCookie),

    clear: () => client.delete<void>('/api/cart/', withCookie),

    /** Login required: moves the guest cart (cookie) into the customer's cart. */
    merge: () => client.post<Cart>('/api/cart/merge/', undefined, withCookie),

    favorites: (signal?: AbortSignal) =>
      client.get<Favorites>('/api/cart/favorites/', { ...withCookie, signal }),

    addFavorite: (productId: Uuid) =>
      client.post<Favorites>('/api/cart/favorites/', { product_id: productId }, withCookie),

    removeFavorite: (productId: Uuid) =>
      client.delete<void>(`/api/cart/favorites/${seg(productId)}/`, withCookie),
  }
}

export function orderEndpoints(client: ApiClient) {
  return {
    /** The key must be reused for retries of the same submit, so it is always passed in. */
    checkout: (body: CheckoutRequest, idempotencyKey: string) =>
      client.post<CheckoutResult>('/api/orders/checkout/', body, { idempotencyKey }),

    /** Lightweight status for polling. */
    status: (orderId: Uuid, signal?: AbortSignal) =>
      client.get<OrderStatusInfo>(`/api/orders/${seg(orderId)}/status/`, { signal }),

    detail: (orderId: Uuid, signal?: AbortSignal) =>
      client.get<Order>(`/api/orders/${seg(orderId)}/`, { signal }),

    list: (params: OrderListParams = {}, signal?: AbortSignal) =>
      client.get<Paginated<OrderSummary>>('/api/orders/', { query: params, signal }),

    cancel: (orderId: Uuid) => client.post<Order>(`/api/orders/${seg(orderId)}/cancel/`),

    /** Dev only: 404 when mock payments are disabled on the server. */
    payMock: (orderId: Uuid) => client.post<Order>(`/api/orders/${seg(orderId)}/pay/mock/`),
  }
}

/** The seller cabinet side of the order service: the caller's sub-orders and sales numbers. */
export function sellerOrderEndpoints(client: ApiClient) {
  const base = '/api/orders/seller'
  return {
    /** Newest first. Statuses go out as one comma separated value. */
    list: ({ status, ...params }: SellerOrderListParams = {}, signal?: AbortSignal) =>
      client.get<Paginated<SellerSubOrder>>(`${base}/`, {
        query: { ...params, status: status?.length ? status.join(',') : undefined },
        signal,
      }),

    detail: (subOrderId: Uuid, signal?: AbortSignal) =>
      client.get<SellerSubOrderDetail>(`${base}/${seg(subOrderId)}/`, { signal }),

    /**
     * 409 `INVALID_TRANSITION` when the sub-order already moved on, `ORDER_NOT_ACTIVE` when the
     * order is no longer being fulfilled; 400 when the tracking number or reason is missing.
     */
    setStatus: (subOrderId: Uuid, body: SubOrderStatusChangeRequest) =>
      client.patch<SellerSubOrderDetail>(`${base}/${seg(subOrderId)}/status/`, body),

    stats: (signal?: AbortSignal) => client.get<SellerStats>(`${base}/stats/`, { signal }),
  }
}

/**
 * Search filters as a query string. `attr` becomes one `attr[<code>]` key per code, repeated
 * once per value; codes and values are sorted so equal filters give the same URL.
 */
export function searchQuery({ attr, ...params }: SearchParams): Query {
  const query: Query = { ...params }
  for (const code of Object.keys(attr ?? {}).sort()) {
    const values = [...new Set(attr![code])].filter(Boolean).sort()
    if (values.length > 0) query[`attr[${code}]`] = values
  }
  return query
}

/** Product search (the shop's listings) and search box suggestions. */
export function searchEndpoints(client: ApiClient) {
  return {
    /** 400 `VALIDATION_ERROR` for bad filters, 503 `SEARCH_UNAVAILABLE` when the index is down. */
    search: (params: SearchParams = {}, signal?: AbortSignal) =>
      client.get<SearchResponse>('/api/search', { query: searchQuery(params), signal }),

    /** Up to 8 titles; empty for queries shorter than 2 characters. */
    suggest: (q: string, signal?: AbortSignal) =>
      client.get<SuggestResponse>('/api/search/suggest', { query: { q }, signal }),
  }
}
