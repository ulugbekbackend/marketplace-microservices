import { ApiError, CLIENT_ERROR, type Category } from '@bozorcha/api-client'
import { describe, expect, it } from 'vitest'
import { safeNext } from './redirect'
import { loginErrorKey, retryAfterSeconds } from './authErrors'
import { findCategoryPath } from './categories'
import { formatE164, formatNational, nationalDigits, toE164 } from './phone'
import { formatMmSs } from './useCountdown'

describe('phone helpers', () => {
  it('formats national numbers progressively', () => {
    expect(formatNational('9')).toBe('9')
    expect(formatNational('901')).toBe('90 1')
    expect(formatNational('901234567')).toBe('90 123 45 67')
    expect(formatNational('90123456789')).toBe('90 123 45 67')
  })

  it('strips a pasted country code', () => {
    expect(nationalDigits('+998 90 123-45-67')).toBe('901234567')
    expect(toE164('90 123 45 67')).toBe('+998901234567')
    expect(formatE164('+998901234567')).toBe('+998 90 123 45 67')
  })
})

describe('login error mapping', () => {
  it('maps known API codes, network and fallbacks', () => {
    expect(loginErrorKey(new ApiError(400, 'OTP_INVALID', 'x'))).toBe('OTP_INVALID')
    expect(loginErrorKey(new ApiError(400, 'OTP_EXPIRED', 'x'))).toBe('OTP_EXPIRED')
    expect(loginErrorKey(new ApiError(403, 'OTP_BLOCKED', 'x'))).toBe('OTP_BLOCKED')
    expect(loginErrorKey(new ApiError(429, 'OTP_RATE_LIMITED', 'x'))).toBe('OTP_RATE_LIMITED')
    expect(loginErrorKey(new ApiError(400, 'INVALID_PHONE', 'x'))).toBe('INVALID_PHONE')
    expect(loginErrorKey(new ApiError(429, 'HTTP_429', 'x'))).toBe('OTP_RATE_LIMITED')
    expect(loginErrorKey(new ApiError(0, CLIENT_ERROR.NETWORK, 'x'))).toBe('network')
    expect(loginErrorKey(new ApiError(500, 'BOOM', 'x'))).toBe('unknown')
    expect(loginErrorKey(new Error('x'))).toBe('unknown')
  })

  it('reads retry_after from details', () => {
    expect(
      retryAfterSeconds(new ApiError(429, 'OTP_RATE_LIMITED', 'x', { retry_after: 41.2 })),
    ).toBe(42)
    expect(retryAfterSeconds(new ApiError(429, 'OTP_RATE_LIMITED', 'x'))).toBeNull()
  })
})

describe('misc', () => {
  it('only allows same-site redirects after login', () => {
    expect(safeNext('/p/choynak?x=1')).toBe('/p/choynak?x=1')
    expect(safeNext('//evil.example')).toBe('/')
    expect(safeNext('https://evil.example')).toBe('/')
    expect(safeNext('/login')).toBe('/')
    expect(safeNext(null)).toBe('/')
  })

  it('finds category ancestry', () => {
    const tree: Category[] = [
      {
        id: '1',
        name: 'Kiyim',
        slug: 'kiyim',
        children: [{ id: '2', name: 'Erkaklar', slug: 'erkaklar', children: [] }],
      },
    ]
    expect(findCategoryPath(tree, 'erkaklar').map((c) => c.slug)).toEqual(['kiyim', 'erkaklar'])
    expect(findCategoryPath(tree, 'yoq')).toEqual([])
  })

  it('formats countdowns', () => {
    expect(formatMmSs(60)).toBe('01:00')
    expect(formatMmSs(5)).toBe('00:05')
  })
})
