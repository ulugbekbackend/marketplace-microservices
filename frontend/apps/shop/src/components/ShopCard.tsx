import { Badge, Card, cn } from '@bozorcha/ui'
import { BadgeCheck, ChevronRight, Store } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

type ShopCardProps = {
  name: string
  slug: string
  productCount?: number
  createdAt?: string
  /** Seller passed the platform's verification. */
  verified?: boolean
  /** Page heading variant (shop page) vs. compact link card (product page). */
  as?: 'heading' | 'link'
  label?: ReactNode
  className?: string
}

export function ShopMonogram({ name, size = 'md' }: { name: string; size?: 'md' | 'lg' }) {
  const letter = name.trim()[0]?.toLocaleUpperCase('uz')
  return (
    <span
      aria-hidden="true"
      className={cn(
        'grid shrink-0 place-items-center rounded-xl bg-primary font-heading font-extrabold text-primary-fg',
        size === 'lg' ? 'size-16 text-3xl' : 'size-12 text-xl',
      )}
    >
      {letter ?? <Store size={22} strokeWidth={1.75} />}
    </span>
  )
}

export function ShopCard({
  name,
  slug,
  productCount,
  createdAt,
  verified,
  as = 'link',
  label,
  className,
}: ShopCardProps) {
  const { t } = useTranslation()
  const year = createdAt ? new Date(createdAt).getUTCFullYear() : null
  const meta = (
    <>
      {productCount !== undefined && (
        <span className="tabular">{t('common.productsCount', { count: productCount })}</span>
      )}
      {year && <span className="tabular">{t('shop.since', { year })}</span>}
    </>
  )

  if (as === 'heading') {
    return (
      <Card padding="lg" className={cn('flex items-center gap-4', className)}>
        <ShopMonogram name={name} size="lg" />
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text [overflow-wrap:anywhere] sm:text-3xl">
            {name}
          </h1>
          {verified && (
            <Badge tone="primary" className="self-start">
              <BadgeCheck aria-hidden="true" size={14} strokeWidth={2} />
              {t('shop.verified')}
            </Badge>
          )}
          <p className="flex flex-wrap gap-x-4 gap-y-0.5 text-sm text-text-muted">{meta}</p>
        </div>
      </Card>
    )
  }

  return (
    <Card padding="none" className={cn('relative', className)}>
      <Link
        to={`/shop/${slug}`}
        className="flex items-center gap-3 rounded-xl p-4 transition-colors duration-150 ease-out hover:bg-surface-2 focus-ring"
      >
        <ShopMonogram name={name} />
        <span className="flex min-w-0 flex-1 flex-col">
          {label && <span className="text-xs text-text-muted">{label}</span>}
          <span className="flex min-w-0 items-center gap-1">
            <span className="truncate font-semibold text-text">{name}</span>
            {verified && (
              <BadgeCheck
                size={16}
                strokeWidth={2}
                className="shrink-0 text-primary"
                role="img"
                aria-label={t('shop.verified')}
              />
            )}
          </span>
          <span className="flex flex-wrap gap-x-3 text-xs text-text-muted">{meta}</span>
        </span>
        <span className="flex shrink-0 items-center gap-0.5 text-sm font-semibold text-primary">
          <span className="hidden sm:inline">{t('product.visitShop')}</span>
          <ChevronRight aria-hidden="true" size={18} strokeWidth={1.75} />
        </span>
      </Link>
    </Card>
  )
}
