import type { ApiClient } from './client'
import type {
  Category,
  OtpVerifyResponse,
  Paginated,
  ProductDetail,
  ProductListItem,
  ProductListParams,
  Shop,
  User,
  UserUpdateRequest,
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
