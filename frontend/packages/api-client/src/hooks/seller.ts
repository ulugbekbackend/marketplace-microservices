import {
  keepPreviousData,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'
import { isApiError, type ApiError } from '../errors'
import type {
  Attribute,
  Paginated,
  SellerApplication,
  SellerApplyRequest,
  SellerProduct,
  SellerProductDetail,
  SellerProductListParams,
  SellerVariant,
  Uuid,
} from '../types'
import { useApi, useSession } from './context'
import { queryKeys } from './keys'

/** How often a product with images still `processing` is re-read. */
export const IMAGE_POLL_INTERVAL_MS = 2_000

/** A pending application is re-checked this often, so approval shows up without a reload. */
export const APPLICATION_POLL_INTERVAL_MS = 30_000

/** The caller's latest seller application; `null` when they have never applied. */
export function useSellerApplication(options: { enabled?: boolean } = {}) {
  const { auth } = useApi()
  const { isAuthenticated } = useSession()
  return useQuery<SellerApplication | null, ApiError>({
    queryKey: queryKeys.sellerApplication,
    queryFn: async ({ signal }) => {
      try {
        return await auth.sellerApplication(signal)
      } catch (error) {
        if (isApiError(error) && error.status === 404) return null
        throw error
      }
    },
    enabled: isAuthenticated && (options.enabled ?? true),
    refetchInterval: (query) =>
      query.state.data?.status === 'pending' ? APPLICATION_POLL_INTERVAL_MS : false,
  })
}

export function useApplySeller() {
  const { auth } = useApi()
  const queryClient = useQueryClient()
  return useMutation<SellerApplication, ApiError, SellerApplyRequest>({
    mutationFn: (body) => auth.applySeller(body),
    onSuccess: (application) => queryClient.setQueryData(queryKeys.sellerApplication, application),
  })
}

/** Attributes with their values, for the variant matrix. They rarely change. */
export function useAttributes() {
  const { seller } = useApi()
  return useQuery<Attribute[], ApiError>({
    queryKey: queryKeys.attributes,
    queryFn: ({ signal }) => seller.attributes(signal),
    staleTime: 10 * 60_000,
  })
}

export function useSellerProducts(params: SellerProductListParams) {
  const { seller } = useApi()
  return useQuery<Paginated<SellerProduct>, ApiError>({
    queryKey: queryKeys.sellerProductList(params),
    queryFn: ({ signal }) => seller.products(params, signal),
    placeholderData: keepPreviousData,
  })
}

const hasProcessingImages = (product: SellerProductDetail | undefined) =>
  Boolean(product?.images.some((image) => image.status === 'processing'))

/** One of the seller's products; re-read every 2 s while an image is being processed. */
export function useSellerProduct(productId: Uuid | undefined, options: { enabled?: boolean } = {}) {
  const { seller } = useApi()
  return useQuery<SellerProductDetail, ApiError>({
    queryKey: queryKeys.sellerProduct(productId ?? ''),
    queryFn: ({ signal }) => seller.product(productId!, signal),
    enabled: Boolean(productId) && (options.enabled ?? true),
    staleTime: 30_000,
    refetchInterval: (query) =>
      hasProcessingImages(query.state.data) ? IMAGE_POLL_INTERVAL_MS : false,
  })
}

/**
 * Details of several products at once (the list has no stock totals). Shares the cache with
 * useSellerProduct, so expanding a row afterwards is instant.
 */
export function useSellerProductDetails(productIds: readonly Uuid[]) {
  const { seller } = useApi()
  return useQueries({
    queries: productIds.map((id) => ({
      queryKey: queryKeys.sellerProduct(id),
      queryFn: ({ signal }: { signal: AbortSignal }) => seller.product(id, signal),
      staleTime: 30_000,
    })),
  })
}

/** Lists show prices and stock flags derived from variants: refresh them after any change. */
export function invalidateSellerLists(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: [...queryKeys.sellerProducts, 'list'] })
}

export type StockUpdateVars = { productId: Uuid; variantId: Uuid; stock: number }

type StockContext = { previous: SellerProductDetail | undefined }

const withVariant = (
  product: SellerProductDetail,
  variantId: Uuid,
  change: (variant: SellerVariant) => SellerVariant,
): SellerProductDetail => ({
  ...product,
  variants: product.variants.map((variant) =>
    variant.id === variantId ? change(variant) : variant,
  ),
})

/**
 * Sets a variant's on-hand stock with an optimistic update of the cached product; the old value
 * comes back if the server refuses (e.g. 409 `STOCK_BELOW_RESERVED`).
 */
export function useUpdateVariantStock() {
  const { seller } = useApi()
  const queryClient = useQueryClient()
  return useMutation<SellerVariant, ApiError, StockUpdateVars, StockContext>({
    mutationFn: ({ variantId, stock }) => seller.setStock(variantId, { stock }),
    onMutate: async ({ productId, variantId, stock }) => {
      const key = queryKeys.sellerProduct(productId)
      await queryClient.cancelQueries({ queryKey: key })
      const previous = queryClient.getQueryData<SellerProductDetail>(key)
      if (previous) {
        queryClient.setQueryData<SellerProductDetail>(
          key,
          withVariant(previous, variantId, (variant) => ({
            ...variant,
            stock,
            available: stock - (variant.reserved ?? 0),
          })),
        )
      }
      return { previous }
    },
    onError: (_error, { productId }, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.sellerProduct(productId), context.previous)
      }
    },
    onSuccess: (variant, { productId }) => {
      queryClient.setQueryData<SellerProductDetail>(queryKeys.sellerProduct(productId), (old) =>
        old ? withVariant(old, variant.id, () => variant) : old,
      )
    },
    onSettled: () => invalidateSellerLists(queryClient),
  })
}
