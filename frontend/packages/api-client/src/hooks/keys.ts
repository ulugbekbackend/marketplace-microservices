import type { ProductListParams } from '../types'

/** Query key factory: one place to build and invalidate cache keys. */
export const queryKeys = {
  me: ['auth', 'me'] as const,
  categories: ['catalog', 'categories'] as const,
  products: (params: ProductListParams) => ['catalog', 'products', params] as const,
  product: (slug: string) => ['catalog', 'product', slug] as const,
  shop: (slug: string) => ['catalog', 'shop', slug] as const,
}
