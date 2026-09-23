import { ImageOff, Store } from 'lucide-react'
import { cn } from '../lib/cn'
import { DefaultLink, type LinkComponent } from '../lib/link'
import { Badge } from './Badge'
import { PriceTag } from './PriceTag'

export type ProductCardProps = {
  href: string
  title: string
  imageUrl: string | null
  /** Lowest variant price, integer tiyin; null when the product has no priced variant. */
  minPrice: number | null
  /** Highest variant price; when it differs from minPrice the card shows "from". */
  maxPrice?: number | null
  sellerName?: string
  inStock: boolean
  labels: {
    outOfStock: string
    /** Suffix for price ranges, e.g. "dan". */
    from: string
    /** Shown instead of a price when minPrice is null. */
    noPrice: string
  }
  /** Router-aware link (e.g. an adapter around React Router's Link). Defaults to `<a>`. */
  linkAs?: LinkComponent
  className?: string
}

export function ProductCard({
  href,
  title,
  imageUrl,
  minPrice,
  maxPrice,
  sellerName,
  inStock,
  labels,
  linkAs: LinkAs = DefaultLink,
  className,
}: ProductCardProps) {
  const hasRange = minPrice !== null && maxPrice != null && maxPrice > minPrice
  return (
    <article
      className={cn(
        'group relative flex min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-soft',
        'transition-colors duration-150 ease-out hover:border-border-strong',
        'focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-primary',
        className,
      )}
    >
      <div className="relative aspect-square overflow-hidden bg-surface-2">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt=""
            loading="lazy"
            decoding="async"
            width={400}
            height={400}
            className={cn('size-full object-cover', !inStock && 'opacity-60 grayscale')}
          />
        ) : (
          <div className="grid size-full place-items-center text-text-muted" aria-hidden="true">
            <ImageOff size={28} strokeWidth={1.75} />
          </div>
        )}
        {!inStock && (
          <Badge tone="neutral" className="absolute top-2 left-2 bg-surface shadow-soft">
            {labels.outOfStock}
          </Badge>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-1.5 p-3">
        {minPrice === null ? (
          <p className="text-sm font-medium text-text-muted">{labels.noPrice}</p>
        ) : (
          <PriceTag price={minPrice} size="sm" suffix={hasRange ? labels.from : undefined} />
        )}
        <h3 className="line-clamp-2 min-h-[2.5rem] text-sm leading-5 font-medium text-text [overflow-wrap:anywhere]">
          {/* The link's pseudo-element stretches over the whole card: one tab stop per product. */}
          <LinkAs
            href={href}
            className="outline-none after:absolute after:inset-0 after:content-[''] focus-visible:outline-none"
          >
            {title}
          </LinkAs>
        </h3>
        {sellerName && (
          <p className="mt-auto flex min-w-0 items-center gap-1 pt-1 text-xs text-text-muted">
            <Store aria-hidden="true" size={14} strokeWidth={1.75} className="shrink-0" />
            <span className="truncate">{sellerName}</span>
          </p>
        )}
      </div>
    </article>
  )
}

export function ProductCardSkeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        'flex flex-col overflow-hidden rounded-xl border border-border bg-surface',
        className,
      )}
    >
      <div className="aspect-square animate-shimmer bg-surface-2 bg-[linear-gradient(90deg,transparent_0%,var(--color-border)_50%,transparent_100%)] bg-[length:200%_100%] bg-no-repeat" />
      <div className="flex flex-col gap-2 p-3">
        <div className="h-5 w-24 rounded-md bg-surface-2" />
        <div className="h-4 w-full rounded-md bg-surface-2" />
        <div className="h-4 w-2/3 rounded-md bg-surface-2" />
        <div className="mt-1 h-3 w-1/2 rounded-md bg-surface-2" />
      </div>
    </div>
  )
}
