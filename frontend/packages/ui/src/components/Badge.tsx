import type { ComponentProps } from 'react'
import { cn } from '../lib/cn'

export type BadgeTone =
  'neutral' | 'muted' | 'primary' | 'accent' | 'info' | 'success' | 'danger' | 'purple'

const tones: Record<BadgeTone, string> = {
  neutral: 'bg-surface-2 text-text',
  muted: 'bg-surface-2 text-text-muted',
  primary: 'bg-primary-soft text-primary',
  accent: 'bg-accent-soft text-accent-ink',
  info: 'bg-info-soft text-info-ink',
  success: 'bg-success-soft text-success-ink',
  danger: 'bg-danger-soft text-danger-ink',
  purple: 'bg-purple-soft text-purple-ink',
}

export type BadgeProps = ComponentProps<'span'> & {
  tone?: BadgeTone
  /** Adds a leading status dot. */
  dot?: boolean
}

export function Badge({ tone = 'neutral', dot, className, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-semibold whitespace-nowrap',
        tones[tone],
        className,
      )}
      {...props}
    >
      {dot && <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  )
}

export type OrderStatus =
  | 'PENDING'
  | 'RESERVED'
  | 'PAID'
  | 'ACCEPTED'
  | 'FULFILLING'
  | 'SHIPPED'
  | 'DELIVERED'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'CANCELLED_BY_SELLER'
  | 'REFUNDED'
  | 'EXPIRED'

/** Order status -> badge tone. Identical in the shop and the seller cabinet. */
export const ORDER_STATUS_TONE: Record<OrderStatus, BadgeTone> = {
  PENDING: 'neutral',
  RESERVED: 'info',
  PAID: 'success',
  ACCEPTED: 'info',
  FULFILLING: 'info',
  SHIPPED: 'purple',
  DELIVERED: 'primary',
  COMPLETED: 'primary',
  CANCELLED: 'danger',
  CANCELLED_BY_SELLER: 'danger',
  REFUNDED: 'danger',
  EXPIRED: 'muted',
}

export type OrderStatusBadgeProps = Omit<BadgeProps, 'tone'> & {
  status: OrderStatus
}

/** Pass the localized label as children; falls back to the raw status code. */
export function OrderStatusBadge({ status, children, ...props }: OrderStatusBadgeProps) {
  return (
    <Badge tone={ORDER_STATUS_TONE[status]} dot data-status={status} {...props}>
      {children ?? status}
    </Badge>
  )
}
