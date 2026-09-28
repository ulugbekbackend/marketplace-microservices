import { useId, type ComponentProps, type ReactNode } from 'react'
import { cn } from '../lib/cn'
import { Field, controlBase, describedBy } from './Field'

export type TextareaProps = ComponentProps<'textarea'> & {
  label?: ReactNode
  hint?: ReactNode
  error?: ReactNode
  wrapperClassName?: string
}

export function Textarea({
  id,
  label,
  hint,
  error,
  className,
  wrapperClassName,
  rows = 4,
  ...props
}: TextareaProps) {
  const autoId = useId()
  const textareaId = id ?? autoId
  return (
    <Field id={textareaId} label={label} hint={hint} error={error} className={wrapperClassName}>
      <textarea
        id={textareaId}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(textareaId, hint, error)}
        className={cn(controlBase, 'min-h-24 resize-y px-3 py-2.5 leading-normal', className)}
        {...props}
      />
    </Field>
  )
}
