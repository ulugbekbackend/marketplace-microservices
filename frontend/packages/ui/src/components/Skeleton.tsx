import type { ComponentProps } from 'react'
import { cn } from '../lib/cn'

/** Decorative loading placeholder. Wrap groups in an element with `aria-busy` + a label. */
export function Skeleton({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      aria-hidden="true"
      data-skeleton=""
      className={cn(
        'animate-shimmer rounded-lg bg-surface-2 bg-[linear-gradient(90deg,transparent_0%,var(--color-border)_50%,transparent_100%)] bg-[length:200%_100%] bg-no-repeat',
        className,
      )}
      {...props}
    />
  )
}
