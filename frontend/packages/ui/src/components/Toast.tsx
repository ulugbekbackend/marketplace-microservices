import { CircleAlert, CircleCheck, Info, X } from 'lucide-react'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

export type ToastTone = 'info' | 'success' | 'danger'

export type ToastOptions = {
  title: ReactNode
  description?: ReactNode
  tone?: ToastTone
  /** Milliseconds before auto-dismiss; 0 keeps it until closed. */
  duration?: number
}

type ToastItem = ToastOptions & { id: number }

type ToastContextValue = {
  toast: (options: ToastOptions) => number
  dismiss: (id: number) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

const toneIcon: Record<ToastTone, ReactNode> = {
  info: <Info aria-hidden="true" size={20} strokeWidth={1.75} className="text-info-ink" />,
  success: (
    <CircleCheck aria-hidden="true" size={20} strokeWidth={1.75} className="text-success-ink" />
  ),
  danger: (
    <CircleAlert aria-hidden="true" size={20} strokeWidth={1.75} className="text-danger-ink" />
  ),
}

export type ToastProviderProps = {
  children: ReactNode
  closeLabel: string
  /** Accessible name of the notifications region. */
  regionLabel: string
}

export function ToastProvider({ children, closeLabel, regionLabel }: ToastProviderProps) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const toast = useCallback((options: ToastOptions) => {
    const id = nextId.current++
    // Keep at most three visible; the newest replaces the oldest.
    setToasts((current) => [...current.slice(-2), { tone: 'info', duration: 4000, ...options, id }])
    return id
  }, [])

  const value = useMemo(() => ({ toast, dismiss }), [toast, dismiss])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <section
        aria-label={regionLabel}
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 p-4 sm:items-end"
      >
        {toasts.map((item) => (
          <ToastView key={item.id} item={item} closeLabel={closeLabel} onDismiss={dismiss} />
        ))}
      </section>
    </ToastContext.Provider>
  )
}

function ToastView({
  item,
  closeLabel,
  onDismiss,
}: {
  item: ToastItem
  closeLabel: string
  onDismiss: (id: number) => void
}) {
  useEffect(() => {
    if (!item.duration) return
    const timer = window.setTimeout(() => onDismiss(item.id), item.duration)
    return () => window.clearTimeout(timer)
  }, [item.id, item.duration, onDismiss])

  return (
    <div className="pointer-events-auto flex w-full max-w-sm animate-toast-in items-start gap-3 rounded-xl border border-border bg-surface p-3 pl-4 text-text shadow-soft">
      <span className="mt-0.5 shrink-0">{toneIcon[item.tone ?? 'info']}</span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold">{item.title}</p>
        {item.description && <p className="mt-0.5 text-sm text-text-muted">{item.description}</p>}
      </div>
      <button
        type="button"
        aria-label={closeLabel}
        onClick={() => onDismiss(item.id)}
        className="grid size-8 shrink-0 place-items-center rounded-lg text-text-muted hover:bg-surface-2 hover:text-text focus-ring"
      >
        <X aria-hidden="true" size={16} strokeWidth={1.75} />
      </button>
    </div>
  )
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside <ToastProvider>')
  return context
}
