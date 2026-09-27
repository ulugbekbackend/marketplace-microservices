import type { ApiClient } from './client'
import type {
  Cart,
  CartAddItemRequest,
  CartUpdateItemRequest,
  Category,
  Favorites,
  OtpVerifyResponse,
  Paginated,
  ProductDetail,
  ProductListItem,
  ProductListParams,
  Shop,
  User,
  UserUpdateRequest,
  Uuid,
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
