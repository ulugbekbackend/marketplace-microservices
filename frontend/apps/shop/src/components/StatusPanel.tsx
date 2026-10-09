import { cn } from '@bozorcha/ui'
import type { ReactNode } from 'react'

const panelTones = {
  info: 'border-info/30 bg-info-soft text-info-ink',
  success: 'border-success/30 bg-success-soft text-success-ink',
  primary: 'border-primary/30 bg-primary-soft text-primary',
  danger: 'border-danger/30 bg-danger-soft text-danger-ink',
  muted: 'border-border bg-surface-2 text-text-muted',
} as const

export type PanelTone = keyof typeof panelTones

/** The order status banner: icon, title, optional hint and actions. `live` announces changes. */
export function StatusPanel({
  tone,
  icon,
  title,
  hint,
  actions,
  live,
}: {
  tone: PanelTone
  icon: ReactNode
  title: string
  hint?: string
  actions?: ReactNode
  live?: boolean
}) {
  return (
    <div
      role={live ? 'status' : undefined}
      data-testid="status-panel"
      className={cn(
        'flex flex-col gap-4 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5',
        panelTones[tone],
      )}
    >
      <div className="flex items-start gap-3">
        <span aria-hidden="true" className="mt-0.5 shrink-0">
          {icon}
        </span>
        <div className="flex flex-col gap-1">
          <p className="font-heading text-lg font-bold">{title}</p>
          {hint && <p className="text-sm text-text">{hint}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap gap-2 sm:shrink-0">{actions}</div>}
    </div>
  )
}
