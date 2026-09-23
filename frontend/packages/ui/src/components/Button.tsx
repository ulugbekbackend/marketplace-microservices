import type { ComponentProps, ReactNode } from 'react'
import { cn } from '../lib/cn'
import { Spinner } from './Spinner'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'accent'
export type ButtonSize = 'sm' | 'md' | 'lg' | 'icon'

const variants: Record<ButtonVariant, string> = {
  primary: 'bg-primary text-primary-fg hover:bg-primary-hover',
  accent: 'bg-accent text-accent-fg hover:bg-accent-hover',
  secondary: 'border border-border bg-surface text-text hover:bg-surface-2',
  ghost: 'bg-transparent text-text hover:bg-surface-2',
  danger: 'bg-danger text-danger-fg hover:brightness-95',
}

const sizes: Record<ButtonSize, string> = {
  sm: 'h-9 gap-1.5 px-3 text-sm',
  md: 'h-11 gap-2 px-4 text-sm',
  lg: 'h-12 gap-2 px-5 text-base',
  icon: 'size-11 p-0',
}

export type ButtonProps = ComponentProps<'button'> & {
  variant?: ButtonVariant
  size?: ButtonSize
  /** Shows a spinner, keeps the button width and blocks clicks. */
  loading?: boolean
  leadingIcon?: ReactNode
  trailingIcon?: ReactNode
  fullWidth?: boolean
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  leadingIcon,
  trailingIcon,
  fullWidth,
  className,
  children,
  disabled,
  type = 'button',
  onClick,
  ...props
}: ButtonProps) {
  // aria-disabled keeps the button focusable and clickable (e.g. to explain why via a toast)
  // while presenting it as disabled.
  const ariaDisabled = props['aria-disabled'] === true || props['aria-disabled'] === 'true'
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      onClick={(event) => {
        if (loading) return
        onClick?.(event)
      }}
      className={cn(
        'relative inline-flex shrink-0 cursor-pointer select-none items-center justify-center rounded-lg font-semibold whitespace-nowrap',
        'transition-[background-color,color,opacity,filter] duration-150 ease-out focus-ring',
        'disabled:cursor-not-allowed disabled:opacity-50',
        ariaDisabled && 'cursor-not-allowed opacity-50',
        variants[variant],
        sizes[size],
        fullWidth && 'w-full',
        className,
      )}
      {...props}
    >
      <span
        className={cn(
          'inline-flex items-center justify-center gap-[inherit]',
          loading && 'invisible',
        )}
      >
        {leadingIcon}
        {children}
        {trailingIcon}
      </span>
      {loading && (
        <span className="absolute inset-0 grid place-items-center">
          <Spinner />
        </span>
      )}
    </button>
  )
}
