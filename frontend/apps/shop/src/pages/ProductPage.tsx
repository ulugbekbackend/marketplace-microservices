import { useProduct, useShop, type ProductDetail, type ProductVariant } from '@bozorcha/api-client'
import { Button, cn, formatPrice, PriceTag, QtyStepper, Skeleton, useToast } from '@bozorcha/ui'
import { CircleCheck, CircleX, ShoppingCart, TriangleAlert } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'
import { Breadcrumbs } from '../components/Breadcrumbs'
import { Gallery } from '../components/Gallery'
import { QueryError } from '../components/QueryError'
import { isNotFound } from '../lib/errors'
import { ShopCard } from '../components/ShopCard'
import { VariantSelector } from '../components/VariantSelector'
import { findVariant, initialSelection, isBuyable, type Selection } from '../lib/variants'
import { NotFoundPage } from './NotFoundPage'

const LOW_STOCK = 5
/** Per-line quantity limit, also bounded by the variant's `available` units. */
const MAX_QTY = 99

export function ProductPage() {
  const { t } = useTranslation()
  const { slug } = useParams()
  const product = useProduct(slug)

  if (product.isPending) return <ProductSkeleton />
  if (product.isError) {
    if (isNotFound(product.error)) {
      return <NotFoundPage title={t('product.notFound')} description={t('product.notFoundHint')} />
    }
    return (
      <div className="page-container py-10">
        <QueryError
          error={product.error}
          onRetry={() => void product.refetch()}
          retrying={product.isRefetching}
        />
      </div>
    )
  }
  // Keyed so gallery and variant state reset when navigating between products.
  return <ProductView key={product.data.id} product={product.data} />
}

function ProductView({ product }: { product: ProductDetail }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const shop = useShop(product.seller.slug)
  const [selection, setSelection] = useState<Selection>(() => initialSelection(product.variants))
  const variant = findVariant(product.variants, selection)
  const cartHintId = useId()
  const [quantity, setQuantity] = useState(1)
  const buyable = variant !== undefined && isBuyable(variant)
  const maxQty = buyable ? Math.min(variant.available, MAX_QTY) : 1
  // Switching to a variant with fewer units left clamps the chosen quantity.
  const qty = Math.min(quantity, maxQty)
  // Server-side category path, root first; older payloads without it fall back to the leaf.
  const categoryPath = product.breadcrumbs.length > 0 ? product.breadcrumbs : [product.category]
  const description = product.description?.trim() ?? ''

  return (
    <div className="page-container flex flex-col gap-5 pt-5 sm:pt-6">
      <title>{`${product.title} | ${t('common.brand')}`}</title>
      <Breadcrumbs
        items={[
          { label: t('catalog.title'), href: '/catalog' },
          ...categoryPath.map((c) => ({ label: c.name, href: `/catalog/${c.slug}` })),
          { label: product.title },
        ]}
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-10">
        <Gallery images={product.images} title={product.title} />

        <div className="flex min-w-0 flex-col gap-5 lg:sticky lg:top-36 lg:self-start">
          <h1 className="font-heading text-2xl leading-tight font-extrabold tracking-tight text-text [overflow-wrap:anywhere] sm:text-3xl">
            {product.title}
          </h1>

          <div className="flex flex-col gap-2" aria-live="polite">
            {variant ? (
              <PriceTag price={variant.price_tiyin} size="lg" />
            ) : product.min_price_tiyin === null ? (
              <p className="text-lg font-medium text-text-muted">{t('product.noPrice')}</p>
            ) : (
              <p className="font-heading text-2xl font-extrabold text-accent-ink tabular sm:text-3xl">
                {product.max_price_tiyin === null ||
                product.max_price_tiyin === product.min_price_tiyin
                  ? formatPrice(product.min_price_tiyin)
                  : `${formatPrice(product.min_price_tiyin)} – ${formatPrice(product.max_price_tiyin)}`}
              </p>
            )}
            <StockLine productInStock={product.in_stock} variant={variant} />
            {variant && (
              <p className="text-xs text-text-muted tabular">
                {t('product.sku', { sku: variant.sku })}
              </p>
            )}
          </div>

          <VariantSelector
            variants={product.variants}
            selection={selection}
            onChange={setSelection}
          />

          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3">
              <QtyStepper
                value={qty}
                onChange={setQuantity}
                max={maxQty}
                disabled={!buyable}
                labels={{
                  group: t('product.quantity'),
                  decrease: t('product.decrease'),
                  increase: t('product.increase'),
                }}
              />
              {buyable && maxQty < MAX_QTY && (
                <span className="text-sm text-text-muted tabular">
                  {t('product.maxQuantity', { count: maxQty })}
                </span>
              )}
            </div>
            <Button
              variant="accent"
              size="lg"
              fullWidth
              aria-disabled="true"
              aria-describedby={cartHintId}
              title={t('product.cartSoon')}
              leadingIcon={<ShoppingCart aria-hidden="true" size={20} strokeWidth={1.75} />}
              onClick={() =>
                toast({ title: t('product.cartSoon'), description: t('product.cartSoonHint') })
              }
            >
              {t('product.addToCart')}
            </Button>
            <p id={cartHintId} className="text-center text-xs text-text-muted">
              {t('product.cartSoon')}
            </p>
          </div>

          <ShopCard
            name={product.seller.shop_name}
            slug={product.seller.slug}
            label={t('product.seller')}
            verified={product.seller.is_verified}
            productCount={shop.data?.product_count}
            createdAt={shop.data?.created_at}
          />
        </div>
      </div>

      <section aria-labelledby="product-description" className="mt-4 flex max-w-3xl flex-col gap-3">
        <h2 id="product-description" className="font-heading text-xl font-bold text-text">
          {t('product.description')}
        </h2>
        {description ? (
          <p className="text-base leading-relaxed whitespace-pre-line text-text [overflow-wrap:anywhere]">
            {description}
          </p>
        ) : (
          <p className="text-text-muted">{t('product.noDescription')}</p>
        )}
      </section>
    </div>
  )
}

function StockLine({
  productInStock,
  variant,
}: {
  productInStock: boolean
  variant: ProductVariant | undefined
}) {
  const { t } = useTranslation()
  if (!variant) {
    return (
      <p className="flex items-center gap-1.5 text-sm text-text-muted">
        <TriangleAlert aria-hidden="true" size={16} strokeWidth={1.75} />
        {productInStock ? t('product.unavailableCombo') : t('product.outOfStock')}
      </p>
    )
  }
  if (!isBuyable(variant)) {
    return (
      <p className="flex items-center gap-1.5 text-sm font-medium text-danger-ink">
        <CircleX aria-hidden="true" size={16} strokeWidth={1.75} />
        {t('product.outOfStock')}
      </p>
    )
  }
  const low = variant.available <= LOW_STOCK
  return (
    <p
      className={cn(
        'flex items-center gap-1.5 text-sm font-medium tabular',
        low ? 'text-accent-ink' : 'text-success-ink',
      )}
    >
      {low ? (
        <TriangleAlert aria-hidden="true" size={16} strokeWidth={1.75} />
      ) : (
        <CircleCheck aria-hidden="true" size={16} strokeWidth={1.75} />
      )}
      {low
        ? t('product.lowStock', { count: variant.available })
        : t('product.available', { count: variant.available })}
    </p>
  )
}

function ProductSkeleton() {
  const { t } = useTranslation()
  return (
    <div
      className="page-container flex flex-col gap-5 pt-5 sm:pt-6"
      role="status"
      aria-busy="true"
      aria-label={t('common.loading')}
    >
      <Skeleton className="h-4 w-64 max-w-full" />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-10">
        <div className="flex flex-col gap-3">
          <Skeleton className="aspect-square w-full rounded-xl" />
          <div className="flex gap-2">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="size-16 sm:size-20" />
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-4">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-2/3" />
          <Skeleton className="h-10 w-48" />
          <Skeleton className="h-4 w-32" />
          <div className="flex gap-2">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-10 w-14" />
            ))}
          </div>
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-20 w-full rounded-xl" />
        </div>
      </div>
    </div>
  )
}
