import type { OrderStatus } from '@bozorcha/api-client'

/**
 * The dev-only "To'lash (test)" button: on in the Vite dev server, and in builds made with
 * `VITE_MOCK_PAYMENT=true`. The server still decides; it answers 404 when mock payments are off.
 */
export const MOCK_PAYMENT_ENABLED =
  import.meta.env.DEV || import.meta.env.VITE_MOCK_PAYMENT === 'true'

/** Short, human-friendly order number: the first block of the UUID. */
export const orderNumber = (id: string) => `#${id.slice(0, 8).toUpperCase()}`

/** The customer can still cancel. */
export const isCancellable = (status: OrderStatus) => status === 'PENDING' || status === 'RESERVED'

/** Reasons of status changes the customer is told about (cancel reasons and payment ones). */
export const ORDER_REASONS = [
  'OUT_OF_STOCK',
  'RESERVATION_FAILED',
  'CANCELLED_BY_CUSTOMER',
  'RESERVATION_EXPIRED',
  'LATE_PAYMENT',
  'LATE_PAYMENT_OUT_OF_STOCK',
  'PAYMENT_REFUNDED',
] as const

export type OrderReason = (typeof ORDER_REASONS)[number]

/** Known reasons only; anything else is not shown to the customer. */
export const knownReason = (reason: string | null | undefined): OrderReason | null =>
  ORDER_REASONS.find((r) => r === reason) ?? null

/** The reason of the latest move into `status`, if the customer is told about it. */
export function lastReasonFor(
  history: readonly { to_status: OrderStatus; reason: string }[],
  status: OrderStatus,
): OrderReason | null {
  const entry = [...history].reverse().find((h) => h.to_status === status)
  return knownReason(entry?.reason)
}

/** Paid after the deadline: the order waits for a second reservation (then PAID or REFUNDED). */
export const awaitsLateReservation = (order: { status: OrderStatus; late_payment?: boolean }) =>
  order.status === 'EXPIRED' && order.late_payment === true
