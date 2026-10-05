import type { SearchItem } from '@bozorcha/api-client'
import { cn, ProductCard, ProductCardSkeleton } from '@bozorcha/ui'
import { useTranslation } from 'react-i18next'
import { RouterLink } from './RouterLink'

const layouts = {
  default: 'grid-cols-2 md:grid-cols-3 xl:grid-cols-4',
  wide: 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5',
} as const

type ProductGridProps = {
  items?: SearchItem[]
  loading?: boolean
  skeletonCount?: number
  layout?: keyof typeof layouts
  /** Hide the shop line, e.g. on the shop's own page. */
  hideSeller?: boolean
  className?: string
}

export function ProductGrid({
  items,
  loading,
  skeletonCount = 8,
  layout = 'default',
  hideSeller,
  className,
}: ProductGridProps) {
  const { t } = useTranslation()
  const gridClass = cn('grid gap-3 sm:gap-4', layouts[layout], className)

  if (loading) {
    return (
      <div className={gridClass} aria-busy="true" aria-label={t('common.loading')} role="status">
        {Array.from({ length: skeletonCount }, (_, i) => (
          <ProductCardSkeleton key={i} />
        ))}
      </div>
    )
  }

  return (
    <ul className={gridClass} aria-label={t('catalog.listLabel')}>
      {items?.map((product) => (
        <li key={product.id} className="flex min-w-0">
          <ProductCard
            className="w-full"
            href={`/p/${product.slug}`}
            title={product.title}
            imageUrl={product.image_url ?? null}
            minPrice={product.min_price}
            maxPrice={product.max_price}
            sellerName={hideSeller ? undefined : product.shop_name}
            inStock={product.in_stock}
            labels={{
              outOfStock: t('product.outOfStock'),
              from: t('product.from'),
              noPrice: t('product.noPrice'),
            }}
            linkAs={RouterLink}
          />
        </li>
      ))}
    </ul>
  )
}
