import type { ComponentProps, ReactNode } from 'react'
import { cn } from '../lib/cn'
import { ORDER_STATUS_TONE, type BadgeTone, type OrderStatus } from './Badge'

export type TimelineTone = 'neutral' | 'primary' | 'info' | 'success' | 'purple' | 'danger'

export type TimelineItem = {
  id: string
  title: ReactNode
  /** Visible time, e.g. "27.09.2026, 17:42". */
  time?: ReactNode
  /** Machine-readable time for `<time dateTime>`. */
  dateTime?: string
  description?: ReactNode
  tone?: TimelineTone
}

export type TimelineProps = Omit<ComponentProps<'ol'>, 'children'> & {
  /** Events that happened, oldest first. The last one is the current step. */
  items: TimelineItem[]
  /** Steps still ahead, shown muted after the current one (e.g. "Yetkaziladi"). */
  upcoming?: Array<Pick<TimelineItem, 'id' | 'title' | 'description'>>
  /** Accessible name of the list. */
  label: string
  /** Tighter spacing for cards inside cards. */
  compact?: boolean
}

const dotTone: Record<TimelineTone, { past: string; current: string }> = {
  neutral: { past: 'border-text-muted', current: 'border-text-muted bg-text-muted ring-surface-2' },
  primary: { past: 'border-primary', current: 'border-primary bg-primary ring-primary-soft' },
  info: { past: 'border-info', current: 'border-info bg-info ring-info-soft' },
  success: { past: 'border-success', current: 'border-success bg-success ring-success-soft' },
  purple: { past: 'border-purple', current: 'border-purple bg-purple ring-purple-soft' },
  danger: { past: 'border-danger', current: 'border-danger bg-danger ring-danger-soft' },
}

const BADGE_TO_TIMELINE: Record<BadgeTone, TimelineTone> = {
  neutral: 'neutral',
  muted: 'neutral',
  accent: 'primary',
  primary: 'primary',
  info: 'info',
  success: 'success',
  purple: 'purple',
  danger: 'danger',
}

/** Dot colour of a status event: the same colour family as the status badge. */
export const orderStatusTimelineTone = (status: OrderStatus): TimelineTone =>
  BADGE_TO_TIMELINE[ORDER_STATUS_TONE[status]]

/**
 * Vertical history of status changes (Stepper/Timeline of the design system). The latest event
 * is marked as the current step; upcoming steps follow in a muted, dashed style.
 */
export function Timeline({
  items,
  upcoming = [],
  label,
  compact = false,
  className,
  ...props
}: TimelineProps) {
  const total = items.length + upcoming.length
  const gap = compact ? 'pb-3' : 'pb-5'
  return (
    <ol aria-label={label} className={cn('flex flex-col', className)} {...props}>
      {items.map((item, index) => {
        const current = index === items.length - 1
        const tone = dotTone[item.tone ?? 'primary']
        const hasNext = index < total - 1
        return (
          <li
            key={item.id}
            aria-current={current ? 'step' : undefined}
            data-state={current ? 'current' : 'done'}
            className={cn('relative flex gap-3', hasNext && gap)}
          >
            {hasNext && (
              <span
                aria-hidden="true"
                className="absolute top-4 bottom-0 left-[5px] w-0.5 rounded-full bg-border"
              />
            )}
            <span
              aria-hidden="true"
              className={cn(
                'relative mt-1 size-3 shrink-0 rounded-full border-2 bg-surface',
                current ? cn(tone.current, 'ring-4') : tone.past,
              )}
            />
            <div className="flex min-w-0 flex-col gap-0.5">
              <span
                className={cn(
                  'text-sm [overflow-wrap:anywhere] text-text',
                  current && 'font-semibold',
                )}
              >
                {item.title}
              </span>
              {item.time && (
                <time dateTime={item.dateTime} className="text-xs text-text-muted tabular">
                  {item.time}
                </time>
              )}
              {item.description && (
                <span className="text-sm [overflow-wrap:anywhere] text-text-muted">
                  {item.description}
                </span>
              )}
            </div>
          </li>
        )
      })}
      {upcoming.map((step, index) => {
        const hasNext = items.length + index < total - 1
        return (
          <li
            key={step.id}
            data-state="upcoming"
            className={cn('relative flex gap-3', hasNext && gap)}
          >
            {hasNext && (
              <span
                aria-hidden="true"
                className="absolute top-4 bottom-0 left-[5px] border-l-2 border-dashed border-border"
              />
            )}
            <span
              aria-hidden="true"
              className="relative mt-1 size-3 shrink-0 rounded-full border-2 border-border-strong bg-surface"
            />
            <div className="flex min-w-0 flex-col gap-0.5">
              <span className="text-sm text-text-muted">{step.title}</span>
              {step.description && (
                <span className="text-xs text-text-muted">{step.description}</span>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
