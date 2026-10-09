import { CLIENT_ERROR, isApiError, type PaymentErrorCode } from '@bozorcha/api-client'
import type { TFunction } from 'i18next'

export const PAYMENT_ERROR_KEYS = [
  'ORDER_NOT_PAYABLE',
  'PAYMENT_IN_PROGRESS',
  'ORDER_SERVICE_UNAVAILABLE',
] as const satisfies readonly PaymentErrorCode[]

export type PaymentErrorKey = (typeof PAYMENT_ERROR_KEYS)[number] | 'network' | 'unknown'

/** Maps a failed payment call to a `payment.errors.*` message key. */
export function paymentErrorKey(error: unknown): PaymentErrorKey {
  if (!isApiError(error)) return 'unknown'
  if (error.code === CLIENT_ERROR.NETWORK) return 'network'
  return PAYMENT_ERROR_KEYS.find((code) => code === error.code) ?? 'unknown'
}

export function paymentErrorMessage(t: TFunction, error: unknown): string {
  return t(`payment.errors.${paymentErrorKey(error)}`)
}
