import {
  useLayoutEffect,
  useRef,
  type ChangeEvent,
  type ClipboardEvent,
  type KeyboardEvent,
} from 'react'
import { cn } from '../lib/cn'

export type OtpInputProps = {
  /** Digits entered so far (no gaps), up to `length`. */
  value: string
  onChange: (value: string) => void
  /** Called once all cells are filled. */
  onComplete?: (code: string) => void
  length?: number
  disabled?: boolean
  invalid?: boolean
  autoFocus?: boolean
  /** Accessible name of the whole group, e.g. "Tasdiqlash kodi". */
  label: string
  /** Accessible name per cell, e.g. (i, n) => `${i + 1}-raqam, jami ${n}`. */
  cellLabel: (index: number, length: number) => string
  /** id of an element that describes the input (e.g. an error message). */
  describedBy?: string
  className?: string
}

const onlyDigits = (text: string) => text.replace(/\D/g, '')

export function OtpInput({
  value,
  onChange,
  onComplete,
  length = 6,
  disabled,
  invalid,
  autoFocus,
  label,
  cellLabel,
  describedBy,
  className,
}: OtpInputProps) {
  const refs = useRef<Array<HTMLInputElement | null>>([])
  // Handlers read the latest value synchronously: moving focus fires onFocus before React
  // re-renders with the new value.
  const latest = useRef(value)
  useLayoutEffect(() => {
    latest.current = value
  }, [value])

  const focusCell = (index: number) => {
    const cell = refs.current[Math.max(0, Math.min(index, length - 1))]
    cell?.focus()
    cell?.select()
  }

  const update = (next: string, focusIndex: number) => {
    const trimmed = onlyDigits(next).slice(0, length)
    const previous = latest.current
    latest.current = trimmed
    onChange(trimmed)
    focusCell(focusIndex)
    if (trimmed.length === length && trimmed !== previous) onComplete?.(trimmed)
  }

  /** Inserts digits at `index`, overwriting what follows (typing, paste and SMS autofill). */
  const insertAt = (index: number, digits: string) => {
    const value = latest.current
    const start = digits.length >= length ? 0 : Math.min(index, value.length)
    const next = (value.slice(0, start) + digits + value.slice(start + digits.length)).slice(
      0,
      length,
    )
    update(next, Math.min(start + digits.length, length - 1))
  }

  const onInput = (index: number) => (event: ChangeEvent<HTMLInputElement>) => {
    const digits = onlyDigits(event.target.value)
    if (!digits) return
    // A single cell normally holds one digit; more means autofill or a fast double key press.
    insertAt(index, digits.length > 1 && digits.length < length ? digits.slice(-1) : digits)
  }

  const onKeyDown = (index: number) => (event: KeyboardEvent<HTMLInputElement>) => {
    const value = latest.current
    switch (event.key) {
      case 'Backspace': {
        event.preventDefault()
        if (value[index] !== undefined) {
          update(value.slice(0, index) + value.slice(index + 1), index)
        } else if (index > 0) {
          update(value.slice(0, index - 1) + value.slice(index), index - 1)
        }
        break
      }
      case 'Delete': {
        event.preventDefault()
        update(value.slice(0, index) + value.slice(index + 1), index)
        break
      }
      case 'ArrowLeft':
        event.preventDefault()
        focusCell(index - 1)
        break
      case 'ArrowRight':
        event.preventDefault()
        focusCell(Math.min(index + 1, value.length))
        break
      case 'Home':
        event.preventDefault()
        focusCell(0)
        break
      case 'End':
        event.preventDefault()
        focusCell(value.length)
        break
    }
  }

  const onPaste = (index: number) => (event: ClipboardEvent<HTMLInputElement>) => {
    event.preventDefault()
    const digits = onlyDigits(event.clipboardData.getData('text'))
    if (digits) insertAt(index, digits)
  }

  return (
    <div
      role="group"
      aria-label={label}
      aria-describedby={describedBy}
      className={cn('grid w-full max-w-sm grid-cols-6 gap-2', className)}
    >
      {Array.from({ length }, (_, index) => (
        <input
          key={index}
          ref={(node) => {
            refs.current[index] = node
          }}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete={index === 0 ? 'one-time-code' : 'off'}
          // eslint-disable-next-line jsx-a11y/no-autofocus -- the OTP step exists only to enter this code
          autoFocus={autoFocus && index === 0}
          aria-label={cellLabel(index, length)}
          aria-invalid={invalid || undefined}
          disabled={disabled}
          value={value[index] ?? ''}
          onChange={onInput(index)}
          onKeyDown={onKeyDown(index)}
          onPaste={onPaste(index)}
          onFocus={(event) => {
            // No gaps: jump to the first empty cell when clicking further right.
            if (index > latest.current.length) focusCell(latest.current.length)
            else event.target.select()
          }}
          className={cn(
            'aspect-square h-auto w-full min-w-0 rounded-lg border border-border bg-surface-2 text-center font-heading text-2xl font-bold text-text tabular',
            'caret-primary transition-colors duration-150 ease-out',
            'focus-visible:border-primary focus-visible:bg-surface focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-primary',
            'disabled:opacity-60',
            value[index] !== undefined && 'border-border-strong bg-surface',
            invalid && 'border-danger bg-danger-soft',
          )}
        />
      ))}
    </div>
  )
}
