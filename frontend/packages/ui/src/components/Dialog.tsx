import { X } from 'lucide-react'
import { useId, type ReactNode } from 'react'
import { cn } from '../lib/cn'
import { Overlay } from './Overlay'

export type DialogProps = {
  open: boolean
  onClose: () => void
  title: ReactNode
  description?: ReactNode
  children?: ReactNode
  footer?: ReactNode
  closeLabel: string
  className?: string
}

export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  closeLabel,
  className,
}: DialogProps) {
  const id = useId()
  return (
    <Overlay
      open={open}
      onClose={onClose}
      labelledBy={`${id}-title`}
      describedBy={description ? `${id}-desc` : undefined}
      panelClassName={cn(
        'top-1/2 left-1/2 max-h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2',
        'animate-fade-in rounded-xl border border-border shadow-soft',
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3 p-5 pb-0">
        <div className="min-w-0">
          <h2 id={`${id}-title`} className="font-heading text-lg font-bold">
            {title}
          </h2>
          {description && (
            <p id={`${id}-desc`} className="mt-1 text-sm text-text-muted">
              {description}
            </p>
          )}
        </div>
        <CloseButton label={closeLabel} onClick={onClose} />
      </div>
      {children && <div className="overflow-y-auto p-5">{children}</div>}
      {footer && (
        <div className="flex flex-wrap justify-end gap-2 border-t border-border p-4">{footer}</div>
      )}
    </Overlay>
  )
}

export function CloseButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="-mt-1 -mr-2 grid size-10 shrink-0 place-items-center rounded-lg text-text-muted transition-colors duration-150 ease-out hover:bg-surface-2 hover:text-text focus-ring"
    >
      <X aria-hidden="true" size={20} strokeWidth={1.75} />
    </button>
  )
}
