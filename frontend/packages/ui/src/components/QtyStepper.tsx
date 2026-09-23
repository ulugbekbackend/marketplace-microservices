import { Minus, Plus } from 'lucide-react'
import { useState, type KeyboardEvent } from 'react'
import { cn } from '../lib/cn'

export type QtyStepperProps = {
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  disabled?: boolean
  labels: { group: string; decrease: string; increase: string }
  className?: string
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

export function QtyStepper({
  value,
  onChange,
  min = 1,
  max = 99,
  disabled,
  labels,
  className,
}: QtyStepperProps) {
  // null while the user is not typing: the field then mirrors `value`.
  const [draft, setDraft] = useState<string | null>(null)
  const shown = draft ?? String(value)

  const commit = (next: number) => {
    const clamped = clamp(Number.isNaN(next) ? value : next, min, max)
    setDraft(null)
    if (clamped !== value) onChange(clamped)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    const keys: Record<string, number> = {
      ArrowUp: value + 1,
      ArrowDown: value - 1,
      Home: min,
      End: max,
    }
    const next = keys[event.key]
    if (next !== undefined) {
      event.preventDefault()
      commit(next)
    } else if (event.key === 'Enter') {
      commit(Number.parseInt(shown, 10))
    }
  }

  const buttonClass = cn(
    'grid size-10 place-items-center text-text transition-colors duration-150 ease-out focus-ring',
    'hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40',
  )

  return (
    <div
      role="group"
      aria-label={labels.group}
      className={cn(
        'inline-flex h-11 items-center overflow-hidden rounded-lg border border-border bg-surface',
        className,
      )}
    >
      <button
        type="button"
        className={buttonClass}
        aria-label={labels.decrease}
        disabled={disabled || value <= min}
        onClick={() => commit(value - 1)}
      >
        <Minus aria-hidden="true" size={18} strokeWidth={1.75} />
      </button>
      <input
        type="text"
        inputMode="numeric"
        role="spinbutton"
        aria-label={labels.group}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
        disabled={disabled}
        value={shown}
        onChange={(event) => setDraft(event.target.value.replace(/\D/g, '').slice(0, 2))}
        onBlur={() => commit(Number.parseInt(shown, 10))}
        onKeyDown={onKeyDown}
        className="h-full w-10 bg-transparent text-center text-base font-semibold text-text tabular focus-ring"
      />
      <button
        type="button"
        className={buttonClass}
        aria-label={labels.increase}
        disabled={disabled || value >= max}
        onClick={() => commit(value + 1)}
      >
        <Plus aria-hidden="true" size={18} strokeWidth={1.75} />
      </button>
    </div>
  )
}
