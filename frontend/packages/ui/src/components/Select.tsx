import { ChevronDown } from 'lucide-react'
import { useId, type ComponentProps, type ReactNode } from 'react'
import { cn } from '../lib/cn'
import { Field, controlBase, describedBy } from './Field'

export type SelectOption = { value: string; label: string; disabled?: boolean }

export type SelectProps = ComponentProps<'select'> & {
  label?: ReactNode
  hint?: ReactNode
  error?: ReactNode
  options?: SelectOption[]
  placeholder?: string
  wrapperClassName?: string
}

export function Select({
  id,
  label,
  hint,
  error,
  options,
  placeholder,
  className,
  wrapperClassName,
  children,
  ...props
}: SelectProps) {
  const autoId = useId()
  const selectId = id ?? autoId
  return (
    <Field id={selectId} label={label} hint={hint} error={error} className={wrapperClassName}>
      <div className="relative">
        <select
          id={selectId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(selectId, hint, error)}
          className={cn(controlBase, 'h-11 cursor-pointer appearance-none pr-10 pl-3', className)}
          {...props}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options?.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </option>
          ))}
          {children}
        </select>
        <ChevronDown
          aria-hidden="true"
          size={20}
          strokeWidth={1.75}
          className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-text-muted"
        />
      </div>
    </Field>
  )
}
