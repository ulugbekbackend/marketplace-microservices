import { ApiError, CLIENT_ERROR } from '@bozorcha/api-client'
import { describe, expect, it } from 'vitest'
import { dailyStats, emptyStats, sellerStats } from '../test/fixtures'
import {
  availableActions,
  formatRate,
  hasFieldError,
  isoDay,
  orderNumber,
  readOrdersFilter,
  statusErrorKey,
  toListParams,
  upcomingSteps,
  withParam,
} from './orders'
import { compactSom, dayLabel, hasNoOrders, summarize, toChartPoints, totalCount } from './stats'

describe('orders list filter', () => {
  it('reads status, dates and page from the URL', () => {
    const filter = readOrdersFilter(
      new URLSearchParams('status=SHIPPED&from=2026-09-01&to=2026-09-27&page=3'),
    )
    expect(filter).toEqual({ tab: 'SHIPPED', from: '2026-09-01', to: '2026-09-27', page: 3 })
    expect(toListParams(filter)).toEqual({
      status: ['SHIPPED'],
      date_from: '2026-09-01',
      date_to: '2026-09-27',
      page: 3,
      page_size: 20,
    })
  })

  it('falls back to defaults for unknown or broken values and swaps a reversed range', () => {
    expect(readOrdersFilter(new URLSearchParams('status=LOST&from=2026-02-31&page=-2'))).toEqual({
      tab: 'all',
      from: null,
      to: null,
      page: 1,
    })
    const reversed = readOrdersFilter(new URLSearchParams('from=2026-09-20&to=2026-09-01'))
    expect([reversed.from, reversed.to]).toEqual(['2026-09-01', '2026-09-20'])
    expect(toListParams(readOrdersFilter(new URLSearchParams()))).toEqual({
      status: undefined,
      date_from: undefined,
      date_to: undefined,
      page: 1,
      page_size: 20,
    })
  })

  it('resets the page on every filter change, but not when paging', () => {
    const params = new URLSearchParams('status=NEW&page=4')
    expect(withParam(params, 'from', '2026-09-01').toString()).toBe('status=NEW&from=2026-09-01')
    expect(withParam(params, 'status', null).toString()).toBe('')
    expect(withParam(params, 'page', '5').toString()).toBe('status=NEW&page=5')
  })

  it('validates calendar days', () => {
    expect(isoDay('2026-09-27')).toBe('2026-09-27')
    expect(isoDay('2026-9-27')).toBeNull()
    expect(isoDay('2026-13-01')).toBeNull()
    expect(isoDay(null)).toBeNull()
  })
})

describe('sub-order actions', () => {
  it('follows the server state table', () => {
    expect(availableActions('NEW')).toEqual(['accept', 'cancel'])
    expect(availableActions('ACCEPTED')).toEqual(['ship', 'cancel'])
    expect(availableActions('SHIPPED')).toEqual(['deliver'])
    expect(availableActions('DELIVERED')).toEqual([])
    expect(availableActions('CANCELLED_BY_SELLER')).toEqual([])
    expect(upcomingSteps('ACCEPTED')).toEqual(['SHIPPED', 'DELIVERED'])
    expect(upcomingSteps('CANCELLED_BY_SELLER')).toEqual([])
  })

  it('maps failures to messages', () => {
    expect(statusErrorKey(new ApiError(409, 'INVALID_TRANSITION', 'x'))).toBe(
      'order.errors.INVALID_TRANSITION',
    )
    expect(statusErrorKey(new ApiError(409, 'ORDER_NOT_ACTIVE', 'x'))).toBe(
      'order.errors.ORDER_NOT_ACTIVE',
    )
    expect(statusErrorKey(new ApiError(404, 'NOT_FOUND', 'x'))).toBe('order.errors.NOT_FOUND')
    expect(statusErrorKey(new ApiError(0, CLIENT_ERROR.NETWORK, 'x'))).toBe('order.errors.network')
    expect(statusErrorKey(new ApiError(500, 'BOOM', 'x'))).toBe('order.errors.unknown')
    expect(statusErrorKey(new Error('x'))).toBe('order.errors.unknown')
  })

  it('finds field errors of a 400', () => {
    const error = new ApiError(400, 'VALIDATION_ERROR', 'x', { tracking_number: ['required'] })
    expect(hasFieldError(error, 'tracking_number')).toBe(true)
    expect(hasFieldError(error, 'reason')).toBe(false)
    expect(hasFieldError(new ApiError(409, 'INVALID_TRANSITION', 'x'), 'reason')).toBe(false)
  })

  it('formats numbers and rates', () => {
    expect(orderNumber('a1b2c3d4-0000-4000-8000-000000000001')).toBe('A1B2C3D4')
    expect(formatRate('0.1000')).toBe('10%')
    expect(formatRate('0.0750')).toBe('7,5%')
  })
})

describe('dashboard stats', () => {
  it('maps daily stats to chart points, oldest first, money in tiyin', () => {
    const daily = dailyStats({ 27: [2, 90_000_000] })
    const points = toChartPoints([...daily].reverse())
    expect(points).toHaveLength(30)
    expect(points[0]).toEqual({
      date: '2026-08-29',
      label: '29.08',
      orders: 0,
      gross: 0,
      net: 0,
    })
    expect(points.at(-1)).toEqual({
      date: '2026-09-27',
      label: '27.09',
      orders: 2,
      gross: 90_000_000,
      net: 81_000_000,
    })
  })

  it('summarises the period and finds the best day', () => {
    const summary = summarize(toChartPoints(sellerStats().daily))
    expect(summary).toMatchObject({ orders: 5, gross: 225_000_000, net: 202_500_000 })
    expect(summary.best?.date).toBe('2026-09-26')
    expect(summarize(toChartPoints(emptyStats().daily)).best).toBeNull()
  })

  it('knows a seller without orders and counts all statuses', () => {
    expect(hasNoOrders(emptyStats())).toBe(true)
    expect(hasNoOrders(sellerStats())).toBe(false)
    expect(totalCount(sellerStats().by_status)).toBe(11)
  })

  it('writes compact axis labels in so’m', () => {
    expect(compactSom(0)).toBe('0')
    expect(compactSom(85_000_000)).toBe('850 ming')
    expect(compactSom(120_000_000)).toBe('1,2 mln')
    expect(compactSom(300_000_000_000)).toBe('3 mlrd')
    expect(dayLabel('2026-09-05')).toBe('05.09')
  })
})
