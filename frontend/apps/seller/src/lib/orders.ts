import {
  CLIENT_ERROR,
  isApiError,
  type OrderStatus,
  type SellerOrderErrorCode,
  type SellerOrderListParams,
  type SubOrderStatus,
  type SubOrderTargetStatus,
} from '@bozorcha/api-client'

export const ORDERS_PAGE_SIZE = 20

/** Longest accepted tracking number and cancel reason (server limits). */
export const TRACKING_MAX = 64
export const REASON_MAX = 255

export const SUB_ORDER_STATUSES = [
  'NEW',
  'ACCEPTED',
  'SHIPPED',
  'DELIVERED',
  'CANCELLED_BY_SELLER',
] as const satisfies readonly SubOrderStatus[]

/**
 * Short order number shared with the customer: the first block of the parent order id, so the
 * seller and the customer quote the same number.
 */
export const orderNumber = (orderId: string) => orderId.slice(0, 8).toUpperCase()

/* ------------------------------------------------------------ list filters */

export type OrdersTab = 'all' | SubOrderStatus

export type OrdersFilter = {
  tab: OrdersTab
  from: string | null
  to: string | null
  page: number
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/

/** `YYYY-MM-DD` that is a real calendar day, or null. */
export function isoDay(value: string | null): string | null {
  if (!value || !ISO_DAY.test(value)) return null
  const date = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value ? value : null
}

const isTab = (value: string | null): value is SubOrderStatus =>
  SUB_ORDER_STATUSES.includes(value as SubOrderStatus)

/** Reads the list filter from the URL; unknown or broken values fall back to defaults. */
export function readOrdersFilter(params: URLSearchParams): OrdersFilter {
  const status = params.get('status')
  let from = isoDay(params.get('from'))
  let to = isoDay(params.get('to'))
  // A reversed range would be rejected by the server: read it the way the seller meant it.
  if (from && to && from > to) [from, to] = [to, from]
  return {
    tab: isTab(status) ? status : 'all',
    from,
    to,
    page: Math.max(1, Math.floor(Number(params.get('page'))) || 1),
  }
}

/** The filter as query params of `GET /api/orders/seller/`. */
export function toListParams(filter: OrdersFilter): SellerOrderListParams {
  return {
    status: filter.tab === 'all' ? undefined : [filter.tab],
    date_from: filter.from ?? undefined,
    date_to: filter.to ?? undefined,
    page: filter.page,
    page_size: ORDERS_PAGE_SIZE,
  }
}

/** Sets or removes one URL param; every filter change goes back to the first page. */
export function withParam(params: URLSearchParams, key: string, value: string | null) {
  const next = new URLSearchParams(params)
  if (value) next.set(key, value)
  else next.delete(key)
  if (key !== 'page') next.delete('page')
  return next
}

/* ---------------------------------------------------------------- actions */

export type SubOrderAction = 'accept' | 'ship' | 'deliver' | 'cancel'

export const ACTION_TARGET: Record<SubOrderAction, SubOrderTargetStatus> = {
  accept: 'ACCEPTED',
  ship: 'SHIPPED',
  deliver: 'DELIVERED',
  cancel: 'CANCELLED_BY_SELLER',
}

/** Allowed next steps per status (the server's state table). */
export function availableActions(status: SubOrderStatus): SubOrderAction[] {
  switch (status) {
    case 'NEW':
      return ['accept', 'cancel']
    case 'ACCEPTED':
      return ['ship', 'cancel']
    case 'SHIPPED':
      return ['deliver']
    default:
      return []
  }
}

/** Steps still ahead on the happy path, for the timeline. */
export function upcomingSteps(status: SubOrderStatus): Array<'ACCEPTED' | 'SHIPPED' | 'DELIVERED'> {
  switch (status) {
    case 'NEW':
      return ['ACCEPTED', 'SHIPPED', 'DELIVERED']
    case 'ACCEPTED':
      return ['SHIPPED', 'DELIVERED']
    case 'SHIPPED':
      return ['DELIVERED']
    default:
      return []
  }
}

/** Order states in which sellers may still work on their sub-orders. */
export const isOrderActive = (status: OrderStatus) => status === 'PAID' || status === 'FULFILLING'

/** Commission rate "0.1000" -> "10%", "0.0750" -> "7,5%". */
export function formatRate(rate: string): string {
  const percent = Math.round(Number(rate) * 10_000) / 100
  if (!Number.isFinite(percent)) return ''
  return `${String(percent).replace('.', ',')}%`
}

/* ----------------------------------------------------------------- errors */

export type StatusErrorKey =
  | 'order.errors.INVALID_TRANSITION'
  | 'order.errors.ORDER_NOT_ACTIVE'
  | 'order.errors.NOT_FOUND'
  | 'order.errors.VALIDATION_ERROR'
  | 'order.errors.network'
  | 'order.errors.unknown'

const KNOWN: readonly SellerOrderErrorCode[] = [
  'INVALID_TRANSITION',
  'ORDER_NOT_ACTIVE',
  'NOT_FOUND',
  'VALIDATION_ERROR',
]

/** i18n key of a failed status change. */
export function statusErrorKey(error: unknown): StatusErrorKey {
  if (!isApiError(error)) return 'order.errors.unknown'
  if (error.code === CLIENT_ERROR.NETWORK) return 'order.errors.network'
  if (error.status === 404) return 'order.errors.NOT_FOUND'
  const code = KNOWN.find((known) => known === error.code)
  return code ? `order.errors.${code}` : 'order.errors.unknown'
}

/** 409: the sub-order or its order changed elsewhere; the page must show the fresh state. */
export const isConflict = (error: unknown) => isApiError(error) && error.status === 409

/**
 * True when a 400 `VALIDATION_ERROR` names the field (`details.tracking_number` or
 * `details.reason`). The server's English text is not shown; the form has its own message.
 */
export function hasFieldError(error: unknown, field: 'tracking_number' | 'reason'): boolean {
  if (!isApiError(error) || error.status !== 400) return false
  const details = error.details as Record<string, unknown> | null | undefined
  return Boolean(details && field in details)
}
