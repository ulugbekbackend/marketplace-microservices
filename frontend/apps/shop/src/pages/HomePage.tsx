import { useCategories, useProducts, type Category } from '@bozorcha/api-client'
import { EmptyState, Skeleton } from '@bozorcha/ui'
import { ChevronRight, PackageOpen } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ProductGrid } from '../components/ProductGrid'
import { QueryError } from '../components/QueryError'
import { CategoryIcon } from '../lib/categoryIcon'

const LATEST_COUNT = 10

export function HomePage() {
  const { t } = useTranslation()
  return (
    <div className="page-container flex flex-col gap-10 pt-6 sm:pt-8 lg:gap-12">
      <title>{t('common.brand')}</title>
      <section aria-labelledby="home-title" className="flex flex-col gap-2">
        <h1
          id="home-title"
          className="font-heading text-3xl font-extrabold tracking-tight text-text sm:text-4xl"
        >
          {t('home.title')}
        </h1>
        <p className="max-w-xl text-base text-text-muted">{t('home.subtitle')}</p>
      </section>
      <CategoryBoard />
      <LatestProducts />
    </div>
  )
}

function CategoryBoard() {
  const { t } = useTranslation()
  const { data, isPending, isError, error, refetch, isRefetching } = useCategories()

  return (
    <section aria-labelledby="home-categories" className="flex flex-col gap-4">
      <h2 id="home-categories" className="font-heading text-xl font-bold text-text sm:text-2xl">
        {t('home.categoriesTitle')}
      </h2>
      {isPending ? (
        <div
          className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4"
          role="status"
          aria-busy="true"
          aria-label={t('common.loading')}
        >
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
      ) : isError ? (
        <QueryError error={error} onRetry={() => void refetch()} retrying={isRefetching} />
      ) : data.length === 0 ? (
        <EmptyState
          icon={<PackageOpen size={22} strokeWidth={1.75} />}
          title={t('home.categoriesEmpty')}
        />
      ) : (
        <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
          {data.slice(0, 8).map((category) => (
            <li key={category.id} className="flex min-w-0">
              <CategoryTile category={category} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function CategoryTile({ category }: { category: Category }) {
  const children = category.children.slice(0, 3).map((child) => child.name)
  return (
    <Link
      to={`/catalog/${category.slug}`}
      className="group flex w-full min-w-0 flex-col gap-3 rounded-xl border border-border bg-surface p-4 shadow-soft transition-colors duration-150 ease-out hover:border-primary focus-ring"
    >
      <span className="grid size-10 place-items-center rounded-lg bg-primary-soft text-primary">
        <CategoryIcon slug={category.slug} />
      </span>
      <span className="flex min-w-0 flex-col gap-1">
        <span className="font-heading text-base leading-tight font-bold text-text [overflow-wrap:anywhere] group-hover:text-primary">
          {category.name}
        </span>
        {children.length > 0 && (
          <span className="line-clamp-2 text-sm text-text-muted">{children.join(', ')}</span>
        )}
      </span>
    </Link>
  )
}

function LatestProducts() {
  const { t } = useTranslation()
  const { data, isPending, isError, error, refetch, isRefetching } = useProducts({
    page: 1,
    page_size: LATEST_COUNT,
  })

  return (
    <section aria-labelledby="home-latest" className="flex flex-col gap-4">
      <div className="flex items-end justify-between gap-4">
        <h2 id="home-latest" className="font-heading text-xl font-bold text-text sm:text-2xl">
          {t('home.newProducts')}
        </h2>
        <Link
          to="/catalog"
          className="inline-flex shrink-0 items-center gap-0.5 rounded-md text-sm font-semibold text-primary hover:underline focus-ring"
        >
          {t('common.viewAll')}
          <ChevronRight aria-hidden="true" size={16} strokeWidth={1.75} />
        </Link>
      </div>
      {isPending ? (
        <ProductGrid loading layout="wide" skeletonCount={LATEST_COUNT} />
      ) : isError ? (
        <QueryError error={error} onRetry={() => void refetch()} retrying={isRefetching} />
      ) : data.items.length === 0 ? (
        <EmptyState
          icon={<PackageOpen size={22} strokeWidth={1.75} />}
          title={t('home.newProductsEmpty')}
          description={t('home.newProductsEmptyHint')}
        />
      ) : (
        <ProductGrid items={data.items} layout="wide" />
      )}
    </section>
  )
}
