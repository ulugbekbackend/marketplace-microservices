import { useEffect, useRef, type ReactNode, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '../lib/cn'

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

let openCount = 0

/** Locks body scroll while at least one overlay is open. */
function useScrollLock(active: boolean) {
  useEffect(() => {
    if (!active) return
    openCount += 1
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      openCount -= 1
      if (openCount === 0) document.body.style.overflow = previous
    }
  }, [active])
}

/** Traps Tab inside the panel, closes on Escape and restores focus on close. */
function useFocusTrap(
  panelRef: RefObject<HTMLElement | null>,
  active: boolean,
  onClose: () => void,
) {
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    if (!active) return
    const panel = panelRef.current
    if (!panel) return
    const previouslyFocused = document.activeElement as HTMLElement | null
    const initial = panel.querySelector<HTMLElement>('[data-autofocus]') ?? panel
    initial.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE))
      if (focusable.length === 0) {
        event.preventDefault()
        return
      }
      const first = focusable[0]!
      const last = focusable[focusable.length - 1]!
      if (
        event.shiftKey &&
        (document.activeElement === first || document.activeElement === panel)
      ) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    panel.addEventListener('keydown', onKeyDown)
    return () => {
      panel.removeEventListener('keydown', onKeyDown)
      previouslyFocused?.focus?.()
    }
  }, [active, panelRef])
}

export type OverlayProps = {
  open: boolean
  onClose: () => void
  labelledBy: string
  describedBy?: string
  panelClassName: string
  children: ReactNode
}

/** Shared modal layer for Dialog and Drawer: portal, scrim, focus trap, Escape, scroll lock. */
export function Overlay({
  open,
  onClose,
  labelledBy,
  describedBy,
  panelClassName,
  children,
}: OverlayProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  useScrollLock(open)
  useFocusTrap(panelRef, open, onClose)

  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-50">
      <div
        aria-hidden="true"
        data-testid="overlay-scrim"
        className="absolute inset-0 animate-fade-in bg-scrim"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        tabIndex={-1}
        className={cn('absolute flex flex-col bg-surface text-text outline-none', panelClassName)}
      >
        {children}
      </div>
    </div>,
    document.body,
  )
}
