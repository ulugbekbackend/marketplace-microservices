import { keepPreviousData, useQuery } from '@tanstack/react-query'
import type { ApiError } from '../errors'
import type {
  Category,
  Paginated,
  ProductDetail,
  ProductListItem,
  ProductListParams,
  Shop,
} from '../types'
import { useApi } from './context'
import { queryKeys } from './keys'

export function useCategories() {
  const { catalog } = useApi()
  return useQuery<Category[], ApiError>({
    queryKey: queryKeys.categories,
    queryFn: ({ signal }) => catalog.categories(signal),
    staleTime: 10 * 60_000,
  })
}

export function useProducts(params: ProductListParams, options: { enabled?: boolean } = {}) {
  const { catalog } = useApi()
  return useQuery<Paginated<ProductListItem>, ApiError>({
    queryKey: queryKeys.products(params),
    queryFn: ({ signal }) => catalog.products(params, signal),
    // Keep the current page visible while the next one loads.
    placeholderData: keepPreviousData,
    enabled: options.enabled ?? true,
  })
}

export function useProduct(slug: string | undefined) {
  const { catalog } = useApi()
  return useQuery<ProductDetail, ApiError>({
    queryKey: queryKeys.product(slug ?? ''),
    queryFn: ({ signal }) => catalog.product(slug!, signal),
    enabled: Boolean(slug),
  })
}

export function useShop(slug: string | undefined) {
  const { catalog } = useApi()
  return useQuery<Shop, ApiError>({
    queryKey: queryKeys.shop(slug ?? ''),
    queryFn: ({ signal }) => catalog.shop(slug!, signal),
    enabled: Boolean(slug),
  })
}
