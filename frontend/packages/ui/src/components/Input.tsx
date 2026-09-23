import { useId, type ComponentProps, type ReactNode } from 'react'
import { cn } from '../lib/cn'
import { Field, controlBase, describedBy } from './Field'

export type InputProps = Omit<ComponentProps<'input'>, 'prefix'> & {
  label?: ReactNode
  hint?: ReactNode
  error?: ReactNode
  /** Icon or fixed text shown inside the field before the value (e.g. `+998`). */
  prefix?: ReactNode
  suffix?: ReactNode
  wrapperClassName?: string
}

export function Input({
  id,
  label,
  hint,
  error,
  prefix,
  suffix,
  className,
  wrapperClassName,
  ...props
}: InputProps) {
  const autoId = useId()
  const inputId = id ?? autoId
  const input = (
    <input
      id={inputId}
      aria-invalid={error ? true : undefined}
      aria-describedby={describedBy(inputId, hint, error)}
      className={cn(
        controlBase,
        'h-11 px-3',
        prefix != null && 'pl-11',
        suffix != null && 'pr-11',
        className,
      )}
      {...props}
    />
  )
  return (
    <Field id={inputId} label={label} hint={hint} error={error} className={wrapperClassName}>
      {prefix != null || suffix != null ? (
        <div className="relative">
          {prefix != null && (
            <span className="pointer-events-none absolute inset-y-0 left-0 flex min-w-11 items-center justify-center px-3 text-text-muted">
              {prefix}
            </span>
          )}
          {input}
          {suffix != null && (
            <span className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-text-muted">
              {suffix}
            </span>
          )}
        </div>
      ) : (
        input
      )}
    </Field>
  )
}
