import { useId, type ReactNode } from 'react'
import { cn } from '../lib/cn'
import { CloseButton } from './Dialog'
import { Overlay } from './Overlay'

export type DrawerSide = 'left' | 'right' | 'bottom'

export type DrawerProps = {
  open: boolean
  onClose: () => void
  title: ReactNode
  side?: DrawerSide
  children: ReactNode
  footer?: ReactNode
  closeLabel: string
  className?: string
}

const sides: Record<DrawerSide, string> = {
  left: 'inset-y-0 left-0 w-[min(22rem,calc(100vw-3rem))] animate-drawer-left border-r',
  right: 'inset-y-0 right-0 w-[min(22rem,calc(100vw-3rem))] animate-drawer-right border-l',
  bottom: 'inset-x-0 bottom-0 max-h-[85dvh] animate-drawer-bottom rounded-t-xl border-t',
}

export function Drawer({
  open,
  onClose,
  title,
  side = 'left',
  children,
  footer,
  closeLabel,
  className,
}: DrawerProps) {
  const id = useId()
  return (
    <Overlay
      open={open}
      onClose={onClose}
      labelledBy={`${id}-title`}
      panelClassName={cn('border-border', sides[side], className)}
    >
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <h2 id={`${id}-title`} className="font-heading text-lg font-bold">
          {title}
        </h2>
        <CloseButton label={closeLabel} onClick={onClose} />
      </div>
      <div className="flex-1 overflow-y-auto overscroll-contain p-4">{children}</div>
      {footer && <div className="border-t border-border p-4">{footer}</div>}
    </Overlay>
  )
}
