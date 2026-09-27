import { ApiError, CLIENT_ERROR } from '@bozorcha/api-client'
import { describe, expect, it } from 'vitest'
import i18n from '../i18n'
import { availableFromError, cartErrorKey, cartErrorMessage } from './cartErrors'

describe('cart error mapping', () => {
  it('maps known codes, network failures and fallbacks', () => {
    expect(cartErrorKey(new ApiError(409, 'OUT_OF_STOCK', 'x'))).toBe('OUT_OF_STOCK')
    expect(cartErrorKey(new ApiError(409, 'CART_FULL', 'x'))).toBe('CART_FULL')
    expect(cartErrorKey(new ApiError(503, 'CATALOG_UNAVAILABLE', 'x'))).toBe('CATALOG_UNAVAILABLE')
    expect(cartErrorKey(new ApiError(0, CLIENT_ERROR.NETWORK, 'x'))).toBe('network')
    expect(cartErrorKey(new ApiError(500, 'HTTP_500', 'x'))).toBe('unknown')
    expect(cartErrorKey(new Error('boom'))).toBe('unknown')
  })

  it('reads the units left from OUT_OF_STOCK details', () => {
    expect(availableFromError(new ApiError(409, 'OUT_OF_STOCK', 'x', { available: 4 }))).toBe(4)
    expect(availableFromError(new ApiError(409, 'OUT_OF_STOCK', 'x', null))).toBeNull()
    expect(
      availableFromError(new ApiError(409, 'OUT_OF_STOCK', 'x', { available: 'a' })),
    ).toBeNull()
  })

  it('words out-of-stock by the units left', () => {
    const t = i18n.t
    expect(cartErrorMessage(t, new ApiError(409, 'OUT_OF_STOCK', 'x', { available: 2 }))).toBe(
      'Omborda yetarli emas: faqat 2 ta bor.',
    )
    expect(cartErrorMessage(t, new ApiError(409, 'OUT_OF_STOCK', 'x', { available: 0 }))).toBe(
      'Bu mahsulot omborda tugadi.',
    )
    expect(cartErrorMessage(t, new ApiError(409, 'CART_FULL', 'x'))).toMatch(/Savatcha to'lgan/)
  })
})
