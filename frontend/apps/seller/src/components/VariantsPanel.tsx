import { useSellerProduct } from '@bozorcha/api-client'
import { Badge, Button, cn, formatPrice, Skeleton } from '@bozorcha/ui'
import { RotateCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { variantName } from '../lib/variants'
import { StockEditor } from './StockEditor'

/** Variants of one product with inline stock editing, shown inside an expanded list row. */
export function VariantsPanel({ productId, title }: { productId: string; title: string }) {
  const { t } = useTranslation()
  const product = useSellerProduct(productId)

  if (product.isPending) {
    return (
      <div className="flex flex-col gap-2 py-2" aria-busy="true" aria-label={t('common.loading')}>
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    )
  }
  if (product.isError) {
    return (
      <div role="alert" className="flex flex-wrap items-center gap-3 py-2 text-sm text-danger-ink">
        {t('products.variantsError')}
        <Button
          size="sm"
          variant="secondary"
          onClick={() => void product.refetch()}
          loading={product.isFetching}
          leadingIcon={<RotateCw aria-hidden="true" size={16} strokeWidth={1.75} />}
        >
          {t('common.retry')}
        </Button>
      </div>
    )
  }
  const { variants } = product.data
  if (variants.length === 0) {
    return (
      <p className="py-3 text-sm text-text-muted">
        {t('products.noVariants')}{' '}
        <Link
          to={`/products/${productId}`}
          className="font-semibold text-primary hover:underline focus-ring"
        >
          {t('products.addVariants')}
        </Link>
      </p>
    )
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface">
      <table className="w-full text-sm">
        <caption className="sr-only">{t('products.variantsOf', { title })}</caption>
        <thead>
          <tr className="border-b border-border text-xs text-text-muted">
            <th scope="col" className="px-3 py-2 text-left font-semibold">
              {t('products.variant')}
            </th>
            <th scope="col" className="hidden px-3 py-2 text-left font-semibold sm:table-cell">
              SKU
            </th>
            <th scope="col" className="hidden px-3 py-2 text-right font-semibold sm:table-cell">
              {t('products.price')}
            </th>
            <th scope="col" className="px-3 py-2 text-right font-semibold">
              {t('products.stock')}
            </th>
            <th scope="col" className="px-3 py-2 text-right font-semibold">
              {t('products.reserved')}
            </th>
          </tr>
        </thead>
        <tbody>
          {variants.map((variant) => {
            const name = variantName(variant, t('products.baseVariant'))
            const inactive = variant.is_active === false
            return (
              <tr
                key={variant.id}
                className={cn(
                  'border-b border-border align-top last:border-0',
                  inactive && 'text-text-muted',
                )}
              >
                <td className="px-3 py-2">
                  <span className="font-medium">{name}</span>
                  <span className="block text-xs text-text-muted sm:hidden">{variant.sku}</span>
                  <span className="block text-xs text-text-muted tabular sm:hidden">
                    {formatPrice(variant.price_tiyin)}
                  </span>
                  {inactive && (
                    <Badge tone="muted" className="mt-1">
                      {t('products.inactive')}
                    </Badge>
                  )}
                </td>
                <td className="hidden px-3 py-2 text-xs tabular sm:table-cell">{variant.sku}</td>
                <td className="hidden px-3 py-2 text-right tabular whitespace-nowrap sm:table-cell">
                  {formatPrice(variant.price_tiyin)}
                </td>
                <td className="px-3 py-1.5 text-right">
                  <StockEditor productId={productId} variant={variant} variantName={name} />
                </td>
                <td className="px-3 py-2 text-right tabular">{variant.reserved ?? 0}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
