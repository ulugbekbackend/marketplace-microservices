import type { ComponentProps } from 'react'
import { cn } from '../lib/cn'

/** The lowercase `bozorcha` wordmark in the heading face. */
export function Wordmark({ className, ...props }: ComponentProps<'span'>) {
  return (
    <span
      className={cn(
        'font-heading text-2xl leading-none font-extrabold tracking-tight text-primary lowercase',
        className,
      )}
      {...props}
    >
      bozorcha
    </span>
  )
}
