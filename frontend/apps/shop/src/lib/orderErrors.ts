import {
  CLIENT_ERROR,
  isApiError,
  type OrderErrorCode,
  type UnavailableItem,
} from '@bozorcha/api-client'
import type { TFunction } from 'i18next'

export const ORDER_ERROR_KEYS = [
  'CART_EMPTY',
  'ITEMS_UNAVAILABLE',
  'IDEMPOTENCY_KEY_REQUIRED',
  'IDEMPOTENCY_KEY_INVALID',
  'IDEMPOTENCY_KEY_REUSED',
  'IDEMPOTENCY_IN_PROGRESS',
  'INVALID_TRANSITION',
  'ORDER_EXPIRED',
  'NOT_RESERVED',
  'SERVICE_UNAVAILABLE',
  'VALIDATION_ERROR',
] as const satisfies readonly OrderErrorCode[]

export type OrderErrorKey = (typeof ORDER_ERROR_KEYS)[number] | 'notFound' | 'network' | 'unknown'

/** Maps a failed order call to an `orders.errors.*` message key. */
export function orderErrorKey(error: unknown): OrderErrorKey {
  if (!isApiError(error)) return 'unknown'
  if (error.code === CLIENT_ERROR.NETWORK) return 'network'
  const known = ORDER_ERROR_KEYS.find((code) => code === error.code)
  if (known) return known
  if (error.status === 404) return 'notFound'
  if (error.status === 503) return 'SERVICE_UNAVAILABLE'
  return 'unknown'
}

export function orderErrorMessage(t: TFunction, error: unknown): string {
  return t(`orders.errors.${orderErrorKey(error)}`)
}

const REASONS = ['not_found', 'inactive', 'out_of_stock'] as const

/** The lines named by an `ITEMS_UNAVAILABLE` error; malformed entries are skipped. */
export function unavailableItemsFromError(error: unknown): UnavailableItem[] {
  if (!isApiError(error) || error.code !== 'ITEMS_UNAVAILABLE') return []
  const details = error.details as { items?: unknown } | null | undefined
  if (!details || !Array.isArray(details.items)) return []
  return details.items.flatMap((raw: unknown) => {
    if (typeof raw !== 'object' || raw === null) return []
    const entry = raw as Record<string, unknown>
    const reason = REASONS.find((r) => r === entry.reason)
    if (typeof entry.variant_id !== 'string' || !reason) return []
    const available = typeof entry.available === 'number' ? entry.available : 0
    return [{ variant_id: entry.variant_id, reason, available }]
  })
}
