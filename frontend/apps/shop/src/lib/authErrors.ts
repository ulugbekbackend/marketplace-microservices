import { CLIENT_ERROR, isApiError } from '@bozorcha/api-client'

export const AUTH_ERROR_KEYS = [
  'OTP_INVALID',
  'OTP_EXPIRED',
  'OTP_BLOCKED',
  'OTP_RATE_LIMITED',
  'INVALID_PHONE',
] as const

export type LoginErrorKey = (typeof AUTH_ERROR_KEYS)[number] | 'network' | 'unknown'

/** Maps an API failure from the OTP endpoints to a `login.errors.*` message key. */
export function loginErrorKey(error: unknown): LoginErrorKey {
  if (!isApiError(error)) return 'unknown'
  if (error.code === CLIENT_ERROR.NETWORK) return 'network'
  const known = AUTH_ERROR_KEYS.find((code) => code === error.code)
  if (known) return known
  if (error.status === 429) return 'OTP_RATE_LIMITED'
  return 'unknown'
}

/** Seconds to wait before another code may be requested, when the API says so. */
export function retryAfterSeconds(error: unknown): number | null {
  if (!isApiError(error) || typeof error.details !== 'object' || error.details === null) return null
  const value = (error.details as Record<string, unknown>).retry_after
  return typeof value === 'number' && value > 0 ? Math.ceil(value) : null
}
