import { useCategories, useProducts, type ProductListItem } from '@bozorcha/api-client'
import { Button, Drawer, EmptyState, Pagination, Skeleton } from '@bozorcha/ui'
import { ListTree, PackageOpen, SearchX, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useSearchParams } from 'react-router'
import { Breadcrumbs } from '../components/Breadcrumbs'
import { CategoryTree, CategoryTreeSkeleton } from '../components/CategoryTree'
import { ProductGrid } from '../components/ProductGrid'
import { QueryError } from '../components/QueryError'
import { RouterLink } from '../components/RouterLink'
import { findCategoryPath } from '../lib/categories'
import { NotFoundPage } from './NotFoundPage'

export const CATALOG_PAGE_SIZE = 24

const parsePage = (value: string | null) => {
  const page = Number.parseInt(value ?? '', 10)
  return Number.isFinite(page) && page > 0 ? page : 1
}

/** Client-side match until the search service exposes a query endpoint. */
const matchesQuery = (product: ProductListItem, q: string) => {
  const needle = q.toLocaleLowerCase('uz')
  return (
    product.title.toLocaleLowerCase('uz').includes(needle) ||
    product.seller.shop_name.toLocaleLowerCase('uz').includes(needle)
  )
}

export function CatalogPage() {
  const { t } = useTranslation()
  const { categorySlug } = useParams()
  const [searchParams] = useSearchParams()
  const page = parsePage(searchParams.get('page'))
  const q = searchParams.get('q')?.trim() ?? ''
  const [drawerOpen, setDrawerOpen] = useState(false)

  const categories = useCategories()
  const products = useProducts({ category: categorySlug, page, page_size: CATALOG_PAGE_SIZE })

  const path = useMemo(
    () => (categorySlug && categories.data ? findCategoryPath(categories.data, categorySlug) : []),
    [categories.data, categorySlug],
  )
  const current = path[path.length - 1]
  const heading = current?.name ?? t('catalog.allProducts')

  const visibleItems = useMemo(
    () =>
      q
        ? (products.data?.items ?? []).filter((item) => matchesQuery(item, q))
        : products.data?.items,
    [products.data, q],
  )

  if (categorySlug && categories.isSuccess && path.length === 0) {
    return <NotFoundPage title={t('catalog.notFound')} />
  }

  const hrefFor = (target: number) => {
    const next = new URLSearchParams(searchParams)
    if (target > 1) next.set('page', String(target))
    else next.delete('page')
    const query = next.toString()
    return `/catalog${categorySlug ? `/${categorySlug}` : ''}${query ? `?${query}` : ''}`
  }
  const clearSearchHref = (() => {
    const next = new URLSearchParams(searchParams)
    next.delete('q')
    const query = next.toString()
    return `/catalog${categorySlug ? `/${categorySlug}` : ''}${query ? `?${query}` : ''}`
  })()

  const pageCount = products.data ? Math.ceil(products.data.total / products.data.page_size) : 0
  const activePath = path.map((category) => category.slug)

  const tree = categories.isPending ? (
    <CategoryTreeSkeleton />
  ) : categories.isError ? (
    <QueryError
      error={categories.error}
      onRetry={() => void categories.refetch()}
      retrying={categories.isRefetching}
      className="px-3 py-6"
    />
  ) : (
    <CategoryTree
      categories={categories.data}
      activeSlug={categorySlug}
      activePath={activePath}
      onNavigate={() => setDrawerOpen(false)}
    />
  )

  return (
    <div className="page-container flex flex-col gap-5 pt-5 sm:pt-6">
      <title>{`${heading} | ${t('common.brand')}`}</title>
      <Breadcrumbs
        items={
          categorySlug
            ? [
                { label: t('catalog.title'), href: '/catalog' },
                ...path.map((c) => ({ label: c.name, href: `/catalog/${c.slug}` })),
              ]
            : [{ label: t('catalog.title') }]
        }
      />

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          {categorySlug && categories.isPending ? (
            <Skeleton className="h-9 w-48" />
          ) : (
            <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text [overflow-wrap:anywhere] sm:text-3xl">
              {heading}
            </h1>
          )}
          {products.data && !q && (
            <p className="text-sm text-text-muted tabular">
              {t('common.productsCount', { count: products.data.total })}
            </p>
          )}
        </div>
        <Button
          variant="secondary"
          className="lg:hidden"
          onClick={() => setDrawerOpen(true)}
          leadingIcon={<ListTree aria-hidden="true" size={18} strokeWidth={1.75} />}
        >
          {t('catalog.showCategories')}
        </Button>
      </div>

      {q && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex h-9 max-w-full items-center gap-1 rounded-full bg-primary-soft pr-1 pl-3 text-sm font-medium text-primary">
              <span className="truncate">{t('catalog.searchFor', { q })}</span>
              <Link
                to={clearSearchHref}
                aria-label={t('catalog.clearSearch')}
                className="grid size-7 shrink-0 place-items-center rounded-full hover:bg-surface focus-ring"
              >
                <X aria-hidden="true" size={16} strokeWidth={1.75} />
              </Link>
            </span>
          </div>
          <p className="text-sm text-text-muted">{t('catalog.searchScopeNote')}</p>
        </div>
      )}

      <div className="lg:grid lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-8">
        <aside className="hidden lg:block">
          <div className="sticky top-36">{tree}</div>
        </aside>

        <div className="flex min-w-0 flex-col gap-6">
          {products.isPending ? (
            <ProductGrid loading skeletonCount={12} />
          ) : products.isError ? (
            <QueryError
              error={products.error}
              onRetry={() => void products.refetch()}
              retrying={products.isRefetching}
            />
          ) : !visibleItems || visibleItems.length === 0 ? (
            q ? (
              <EmptyState
                icon={<SearchX size={22} strokeWidth={1.75} />}
                title={t('catalog.searchEmpty', { q })}
                description={t('catalog.searchEmptyHint')}
                action={
                  <Link
                    to={clearSearchHref}
                    className="inline-flex h-11 items-center rounded-lg border border-border bg-surface px-4 text-sm font-semibold text-text hover:bg-surface-2 focus-ring"
                  >
                    {t('catalog.clearSearch')}
                  </Link>
                }
              />
            ) : (
              <EmptyState
                icon={<PackageOpen size={22} strokeWidth={1.75} />}
                title={t('catalog.empty')}
                description={t('catalog.emptyHint')}
              />
            )
          ) : (
            <div
              className={
                products.isPlaceholderData
                  ? 'opacity-60 transition-opacity duration-150'
                  : undefined
              }
              aria-busy={products.isPlaceholderData || undefined}
            >
              <ProductGrid items={visibleItems} />
            </div>
          )}

          <Pagination
            page={page}
            pageCount={pageCount}
            hrefFor={hrefFor}
            linkAs={RouterLink}
            labels={{
              nav: t('catalog.pagination'),
              previous: t('catalog.previousPage'),
              next: t('catalog.nextPage'),
              page: (p) => t('catalog.page', { page: p }),
            }}
          />
        </div>
      </div>

      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={t('catalog.categories')}
        closeLabel={t('common.close')}
        side="left"
      >
        {tree}
      </Drawer>
    </div>
  )
}
