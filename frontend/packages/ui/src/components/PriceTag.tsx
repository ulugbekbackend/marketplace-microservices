import type { ComponentProps, ReactNode } from 'react'
import { cn } from '../lib/cn'
import { discountPercent, formatPrice } from '../lib/format'

export type PriceTagProps = ComponentProps<'div'> & {
  /** Current price, integer tiyin. */
  price: number
  /** Previous price, integer tiyin; shown struck through with a discount badge. */
  oldPrice?: number | null
  size?: 'sm' | 'md' | 'lg'
  /** Small muted text after the price, e.g. "dan" for "from". */
  suffix?: ReactNode
  /** Accessible label for the old price, e.g. "Oldingi narx". */
  oldPriceLabel?: string
}

const sizes = {
  sm: 'text-base',
  md: 'text-lg',
  lg: 'text-2xl sm:text-3xl',
} as const

export function PriceTag({
  price,
  oldPrice,
  size = 'md',
  suffix,
  oldPriceLabel,
  className,
  ...props
}: PriceTagProps) {
  const discount = discountPercent(price, oldPrice)
  return (
    <div className={cn('flex flex-wrap items-baseline gap-x-2 gap-y-1', className)} {...props}>
      <span
        className={cn('font-heading font-extrabold text-accent-ink tabular', sizes[size])}
        data-testid="price"
      >
        {formatPrice(price)}
      </span>
      {suffix && <span className="text-sm text-text-muted">{suffix}</span>}
      {discount !== null && oldPrice != null && (
        <>
          <s className="text-sm text-text-muted tabular">
            {oldPriceLabel && <span className="sr-only">{oldPriceLabel}: </span>}
            {formatPrice(oldPrice)}
          </s>
          <span className="rounded-full bg-accent px-2 py-0.5 text-xs font-bold text-accent-fg tabular">
            -{discount}%
          </span>
        </>
      )}
    </div>
  )
}
