import { CLIENT_ERROR, isApiError, type CartErrorCode } from '@bozorcha/api-client'
import type { TFunction } from 'i18next'

export const CART_ERROR_KEYS = [
  'OUT_OF_STOCK',
  'VARIANT_INACTIVE',
  'VARIANT_NOT_FOUND',
  'NOT_IN_CART',
  'CART_FULL',
  'FAVORITES_FULL',
  'CATALOG_UNAVAILABLE',
  'VALIDATION_ERROR',
] as const satisfies readonly CartErrorCode[]

export type CartErrorKey = (typeof CART_ERROR_KEYS)[number] | 'network' | 'unknown'

/** Maps a failed cart or favorites call to a `cart.errors.*` message key. */
export function cartErrorKey(error: unknown): CartErrorKey {
  if (!isApiError(error)) return 'unknown'
  if (error.code === CLIENT_ERROR.NETWORK) return 'network'
  return CART_ERROR_KEYS.find((code) => code === error.code) ?? 'unknown'
}

/** Units still available, from an `OUT_OF_STOCK` error's details. */
export function availableFromError(error: unknown): number | null {
  if (!isApiError(error) || typeof error.details !== 'object' || error.details === null) return null
  const value = (error.details as Record<string, unknown>).available
  return typeof value === 'number' && value >= 0 ? value : null
}

/** A user-facing Uzbek message for a failed cart call. */
export function cartErrorMessage(t: TFunction, error: unknown): string {
  const key = cartErrorKey(error)
  if (key === 'OUT_OF_STOCK') {
    const available = availableFromError(error)
    return available
      ? t('cart.errors.OUT_OF_STOCK', { count: available })
      : t('cart.errors.OUT_OF_STOCK_none')
  }
  return t(`cart.errors.${key}`)
}
