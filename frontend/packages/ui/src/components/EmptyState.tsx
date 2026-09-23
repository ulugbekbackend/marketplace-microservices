import type { ComponentProps, ReactNode } from 'react'
import { cn } from '../lib/cn'

export type EmptyStateProps = Omit<ComponentProps<'div'>, 'title'> & {
  icon?: ReactNode
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
  tone?: 'neutral' | 'danger'
}

/** Empty or error state: icon + title + optional description and action. */
export function EmptyState({
  icon,
  title,
  description,
  action,
  tone = 'neutral',
  className,
  ...props
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border px-6 py-10 text-center',
        className,
      )}
      {...props}
    >
      {icon && (
        <div
          className={cn(
            'grid size-12 place-items-center rounded-full',
            tone === 'danger' ? 'bg-danger-soft text-danger-ink' : 'bg-surface-2 text-text-muted',
          )}
          aria-hidden="true"
        >
          {icon}
        </div>
      )}
      <h2 className="font-heading text-lg font-bold text-text">{title}</h2>
      {description && <p className="max-w-sm text-sm text-text-muted">{description}</p>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  )
}
