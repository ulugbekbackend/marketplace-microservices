import { useProducts, useShop } from '@bozorcha/api-client'
import { Card, EmptyState, Pagination, Skeleton } from '@bozorcha/ui'
import { PackageOpen } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useParams, useSearchParams } from 'react-router'
import { Breadcrumbs } from '../components/Breadcrumbs'
import { ProductGrid } from '../components/ProductGrid'
import { QueryError } from '../components/QueryError'
import { isNotFound } from '../lib/errors'
import { RouterLink } from '../components/RouterLink'
import { ShopCard } from '../components/ShopCard'
import { NotFoundPage } from './NotFoundPage'

const PAGE_SIZE = 20

export function ShopPage() {
  const { t } = useTranslation()
  const { slug = '' } = useParams()
  const [searchParams] = useSearchParams()
  const page = Math.max(1, Number.parseInt(searchParams.get('page') ?? '1', 10) || 1)
  const shop = useShop(slug)
  const products = useProducts(
    { seller: slug, page, page_size: PAGE_SIZE },
    { enabled: shop.isSuccess },
  )

  if (shop.isError && isNotFound(shop.error)) {
    return <NotFoundPage title={t('shop.notFound')} description={t('shop.notFoundHint')} />
  }

  const pageCount = products.data ? Math.ceil(products.data.total / products.data.page_size) : 0

  return (
    <div className="page-container flex flex-col gap-6 pt-5 sm:pt-6">
      {shop.data && <title>{`${shop.data.shop_name} | ${t('common.brand')}`}</title>}
      {shop.data ? (
        <Breadcrumbs items={[{ label: shop.data.shop_name }]} />
      ) : (
        <Skeleton className="h-5 w-40" />
      )}

      {shop.isPending ? (
        <Card
          padding="lg"
          className="flex items-center gap-4"
          aria-busy="true"
          aria-label={t('common.loading')}
        >
          <Skeleton className="size-16 rounded-xl" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton className="h-8 w-56 max-w-full" />
            <Skeleton className="h-4 w-40" />
          </div>
        </Card>
      ) : shop.isError ? (
        <QueryError
          error={shop.error}
          onRetry={() => void shop.refetch()}
          retrying={shop.isRefetching}
        />
      ) : (
        <ShopCard
          as="heading"
          name={shop.data.shop_name}
          slug={shop.data.slug}
          productCount={shop.data.product_count}
          createdAt={shop.data.created_at}
          verified={shop.data.is_verified}
        />
      )}

      {!shop.isError && (
        <section aria-labelledby="shop-products" className="flex flex-col gap-4">
          <h2 id="shop-products" className="font-heading text-xl font-bold text-text">
            {t('shop.products')}
          </h2>
          {shop.isPending || products.isPending ? (
            <ProductGrid loading layout="wide" skeletonCount={10} />
          ) : products.isError ? (
            <QueryError
              error={products.error}
              onRetry={() => void products.refetch()}
              retrying={products.isRefetching}
            />
          ) : products.data.items.length === 0 ? (
            <EmptyState
              icon={<PackageOpen size={22} strokeWidth={1.75} />}
              title={t('shop.empty')}
              description={t('shop.emptyHint')}
            />
          ) : (
            <ProductGrid items={products.data.items} layout="wide" hideSeller />
          )}
          <Pagination
            page={page}
            pageCount={pageCount}
            hrefFor={(p) => (p > 1 ? `/shop/${slug}?page=${p}` : `/shop/${slug}`)}
            linkAs={RouterLink}
            labels={{
              nav: t('catalog.pagination'),
              previous: t('catalog.previousPage'),
              next: t('catalog.nextPage'),
              page: (p) => t('catalog.page', { page: p }),
            }}
          />
        </section>
      )}
    </div>
  )
}
