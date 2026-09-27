import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { isApiError, type ApiError } from '../errors'
import type { Cart, CartErrorCode, Favorites, Uuid } from '../types'
import { useApi, useSession } from './context'
import { queryKeys } from './keys'

/**
 * Cart mutations share one scope, so they reach the server one at a time and in order. Rapid
 * clicks on a quantity stepper therefore can never let an older response overwrite a newer cart.
 */
const CART_SCOPE = { id: 'cart' }
const FAVORITES_SCOPE = { id: 'favorites' }

/** Errors that mean the cached cart no longer matches the server (stock, removed variants). */
const STALE_CART_CODES: readonly CartErrorCode[] = [
  'OUT_OF_STOCK',
  'VARIANT_INACTIVE',
  'VARIANT_NOT_FOUND',
  'NOT_IN_CART',
]

export const EMPTY_CART: Cart = {
  groups: [],
  total_tiyin: 0,
  items_count: 0,
  has_unavailable: false,
  has_price_changes: false,
  removed: [],
}

function refreshOnStaleError(queryClient: QueryClient, error: unknown) {
  if (isApiError(error) && (STALE_CART_CODES as readonly string[]).includes(error.code)) {
    void queryClient.invalidateQueries({ queryKey: queryKeys.cart })
  }
}

/** Finds a cart line by variant id. */
export function findCartItem(cart: Cart | undefined, variantId: Uuid) {
  for (const group of cart?.groups ?? []) {
    const item = group.items.find((line) => line.variant_id === variantId)
    if (item) return item
  }
  return undefined
}

/** The current cart (guest or customer); available to everyone. */
export function useCart(options: { enabled?: boolean } = {}) {
  const { cart } = useApi()
  return useQuery<Cart, ApiError>({
    queryKey: queryKeys.cart,
    queryFn: ({ signal }) => cart.get(signal),
    enabled: options.enabled ?? true,
  })
}

/** Shared shape of the cart mutations: each returns the full cart, which replaces the cache. */
function useCartMutation<TVars>(mutationFn: (vars: TVars) => Promise<Cart>) {
  const queryClient = useQueryClient()
  return useMutation<Cart, ApiError, TVars>({
    mutationFn,
    scope: CART_SCOPE,
    onSuccess: (data) => queryClient.setQueryData(queryKeys.cart, data),
    onError: (error) => refreshOnStaleError(queryClient, error),
  })
}

export function useAddToCart() {
  const { cart } = useApi()
  return useCartMutation((vars: { variantId: Uuid; qty: number }) =>
    cart.addItem({ variant_id: vars.variantId, qty: vars.qty }),
  )
}

/** Sets a line's quantity; 0 removes it. */
export function useUpdateCartItem() {
  const { cart } = useApi()
  return useCartMutation((vars: { variantId: Uuid; qty: number }) =>
    cart.updateItem(vars.variantId, { qty: vars.qty }),
  )
}

export function useRemoveCartItem() {
  const { cart } = useApi()
  return useCartMutation((vars: { variantId: Uuid }) => cart.removeItem(vars.variantId))
}

export function useClearCart() {
  const { cart } = useApi()
  return useCartMutation<void>(async () => {
    await cart.clear()
    return EMPTY_CART
  })
}

/**
 * Right after login: moves the guest cart into the customer's cart. On failure the cart is
 * refetched, so the header shows the customer's own cart either way.
 */
export function useMergeCart() {
  const { cart } = useApi()
  const queryClient = useQueryClient()
  return useMutation<Cart, ApiError, void>({
    mutationFn: () => cart.merge(),
    scope: CART_SCOPE,
    onSuccess: (data) => queryClient.setQueryData(queryKeys.cart, data),
    onError: () => void queryClient.invalidateQueries({ queryKey: queryKeys.cart }),
  })
}

/** Favorite product ids; only fetched while signed in. */
export function useFavorites() {
  const { cart } = useApi()
  const { isAuthenticated } = useSession()
  return useQuery<Favorites, ApiError>({
    queryKey: queryKeys.favorites,
    queryFn: ({ signal }) => cart.favorites(signal),
    enabled: isAuthenticated,
    staleTime: 5 * 60_000,
  })
}

type ToggleFavoriteVars = { productId: Uuid; favorite: boolean }

/** Adds or removes a favorite; the heart flips at once and rolls back if the call fails. */
export function useToggleFavorite() {
  const { cart } = useApi()
  const queryClient = useQueryClient()
  return useMutation<Favorites | void, ApiError, ToggleFavoriteVars, { previous?: Favorites }>({
    mutationFn: ({ productId, favorite }) =>
      favorite ? cart.addFavorite(productId) : cart.removeFavorite(productId),
    scope: FAVORITES_SCOPE,
    onMutate: async ({ productId, favorite }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.favorites })
      const previous = queryClient.getQueryData<Favorites>(queryKeys.favorites)
      const others = (previous?.items ?? []).filter((id) => id !== productId)
      queryClient.setQueryData<Favorites>(queryKeys.favorites, {
        items: favorite ? [productId, ...others] : others,
      })
      return { previous }
    },
    onSuccess: (data) => {
      if (data) queryClient.setQueryData(queryKeys.favorites, data)
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(queryKeys.favorites, context.previous)
      else void queryClient.invalidateQueries({ queryKey: queryKeys.favorites })
    },
  })
}
