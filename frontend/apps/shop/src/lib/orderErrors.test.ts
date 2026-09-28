import { ApiError, CLIENT_ERROR } from '@bozorcha/api-client'
import { describe, expect, it } from 'vitest'
import i18n from '../i18n'
import { formatDateTime } from './dates'
import { orderErrorKey, orderErrorMessage, unavailableItemsFromError } from './orderErrors'
import { knownReason, orderNumber } from './orders'

describe('order error mapping', () => {
  it('maps service codes, 404, 503, network and fallbacks', () => {
    for (const code of [
      'CART_EMPTY',
      'ITEMS_UNAVAILABLE',
      'IDEMPOTENCY_KEY_REUSED',
      'IDEMPOTENCY_IN_PROGRESS',
      'INVALID_TRANSITION',
      'ORDER_EXPIRED',
      'NOT_RESERVED',
    ]) {
      expect(orderErrorKey(new ApiError(409, code, 'x'))).toBe(code)
    }
    expect(orderErrorKey(new ApiError(404, 'NOT_FOUND', 'x'))).toBe('notFound')
    expect(orderErrorKey(new ApiError(503, 'HTTP_503', 'x'))).toBe('SERVICE_UNAVAILABLE')
    expect(orderErrorKey(new ApiError(0, CLIENT_ERROR.NETWORK, 'x'))).toBe('network')
    expect(orderErrorKey(new ApiError(500, 'HTTP_500', 'x'))).toBe('unknown')
    expect(orderErrorKey('boom')).toBe('unknown')
  })

  it('has an Uzbek message for every key', () => {
    const t = i18n.t
    expect(orderErrorMessage(t, new ApiError(409, 'ORDER_EXPIRED', 'x'))).toBe(
      "To'lov vaqti tugagan. Buyurtma bekor bo'ldi.",
    )
    expect(orderErrorMessage(t, new ApiError(409, 'CART_EMPTY', 'x'))).toMatch(/Savatcha bo'sh/)
    expect(orderErrorMessage(t, new ApiError(400, 'IDEMPOTENCY_KEY_REQUIRED', 'x'))).toMatch(
      /So'rov to'liq emas/,
    )
  })

  it('reads unavailable items, skipping malformed entries', () => {
    const error = new ApiError(409, 'ITEMS_UNAVAILABLE', 'x', {
      items: [
        { variant_id: 'v1', reason: 'out_of_stock', available: 2 },
        { variant_id: 'v2', reason: 'inactive' },
        { variant_id: 3, reason: 'inactive' },
        { variant_id: 'v4', reason: 'weird' },
        null,
      ],
    })
    expect(unavailableItemsFromError(error)).toEqual([
      { variant_id: 'v1', reason: 'out_of_stock', available: 2 },
      { variant_id: 'v2', reason: 'inactive', available: 0 },
    ])
    expect(unavailableItemsFromError(new ApiError(409, 'CART_EMPTY', 'x', {}))).toEqual([])
  })
})

describe('order helpers', () => {
  it('formats numbers, dates, and reasons', () => {
    expect(orderNumber('a1b2c3d4-0000-4000-8000-000000000001')).toBe('#A1B2C3D4')
    expect(formatDateTime('2026-09-27T10:05:00Z')).toMatch(/^27\.09\.2026, \d\d:05$/)
    expect(formatDateTime('nope')).toBe('')
    expect(knownReason('OUT_OF_STOCK')).toBe('OUT_OF_STOCK')
    expect(knownReason('SOMETHING_INTERNAL')).toBeNull()
  })
})
