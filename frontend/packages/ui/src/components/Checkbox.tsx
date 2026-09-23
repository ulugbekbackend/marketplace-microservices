import { Check } from 'lucide-react'
import { useId, type ComponentProps, type ReactNode } from 'react'
import { cn } from '../lib/cn'

export type CheckboxProps = Omit<ComponentProps<'input'>, 'type'> & {
  label: ReactNode
  description?: ReactNode
}

export function Checkbox({ id, label, description, className, ...props }: CheckboxProps) {
  const autoId = useId()
  const inputId = id ?? autoId
  return (
    <div className={cn('flex items-start gap-3', className)}>
      <span className="relative mt-0.5 inline-flex size-5 shrink-0">
        <input
          id={inputId}
          type="checkbox"
          aria-describedby={description ? `${inputId}-desc` : undefined}
          className={cn(
            'peer size-5 cursor-pointer appearance-none rounded-md border border-border-strong bg-surface',
            'transition-colors duration-150 ease-out checked:border-primary checked:bg-primary focus-ring',
            'disabled:cursor-not-allowed disabled:opacity-50',
          )}
          {...props}
        />
        <Check
          aria-hidden="true"
          size={14}
          strokeWidth={3}
          className="pointer-events-none absolute top-[3px] left-[3px] text-primary-fg opacity-0 peer-checked:opacity-100"
        />
      </span>
      <span className="flex min-w-0 flex-col">
        <label htmlFor={inputId} className="cursor-pointer text-sm font-medium text-text">
          {label}
        </label>
        {description && (
          <span id={`${inputId}-desc`} className="text-sm text-text-muted">
            {description}
          </span>
        )}
      </span>
    </div>
  )
}
