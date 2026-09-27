import type { OrderStatus, SubOrderStatus } from '@bozorcha/api-client'
import { ORDER_STATUS_TONE, type BadgeTone } from '@bozorcha/ui'

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

/** Sub-order badges use the shared status colours; a new sub-order looks like a pending one. */
export const subOrderTone = (status: SubOrderStatus): BadgeTone =>
  status === 'NEW' ? ORDER_STATUS_TONE.PENDING : ORDER_STATUS_TONE[status]

export const CANCEL_REASONS = [
  'OUT_OF_STOCK',
  'RESERVATION_FAILED',
  'CANCELLED_BY_CUSTOMER',
  'RESERVATION_EXPIRED',
] as const

export type CancelReason = (typeof CANCEL_REASONS)[number]

/** Known cancel reasons only; anything else is not shown to the customer. */
export const knownReason = (reason: string | null | undefined): CancelReason | null =>
  CANCEL_REASONS.find((r) => r === reason) ?? null
