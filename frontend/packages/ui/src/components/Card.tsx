import type { ComponentProps } from 'react'
import { cn } from '../lib/cn'

export type CardProps = ComponentProps<'div'> & {
  padding?: 'none' | 'sm' | 'md' | 'lg'
}

const paddings = { none: '', sm: 'p-3', md: 'p-4 sm:p-5', lg: 'p-5 sm:p-6' } as const

export function Card({ padding = 'md', className, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-xl border border-border bg-surface text-text shadow-soft',
        paddings[padding],
        className,
      )}
      {...props}
    />
  )
}
