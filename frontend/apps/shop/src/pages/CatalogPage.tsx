import { useCategories, useSearch, type SearchSort } from '@bozorcha/api-client'
import { Button, Drawer, EmptyState, Pagination, Skeleton } from '@bozorcha/ui'
import { ChevronDown, PackageOpen, SearchX, SlidersHorizontal, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { Breadcrumbs } from '../components/Breadcrumbs'
import { FilterPanel } from '../components/catalog/FilterPanel'
import { SearchError } from '../components/catalog/SearchError'
import { ProductGrid } from '../components/ProductGrid'
import { QueryError } from '../components/QueryError'
import { RouterLink } from '../components/RouterLink'
import { findCategoryPath } from '../lib/categories'
import {
  activeFilterCount,
  catalogHref,
  clearFilters,
  effectiveSort,
  hasFilters,
  parseCatalogParams,
  SORTS,
  toggleAttr,
  toSearchParams,
  withFilters,
  type CatalogFilters,
} from '../lib/catalogFilters'
import { attributeLabel, priceRangeLabel, valueLabel } from '../lib/searchLabels'
import { NotFoundPage } from './NotFoundPage'

/**
 * Listing and search results in one page: `/catalog[/<category slug>]?q=&...`. Results,
 * facets and counts come from the search service; the category tree (names, slugs, ids) from
 * the catalog. Every filter lives in the URL (see `lib/catalogFilters`).
 */
export function CatalogPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { categorySlug } = useParams()
  const [searchParams] = useSearchParams()
  const filters = useMemo(() => parseCatalogParams(searchParams), [searchParams])
  const [drawerOpen, setDrawerOpen] = useState(false)

  const categories = useCategories()
  const path = useMemo(
    () => (categorySlug && categories.data ? findCategoryPath(categories.data, categorySlug) : []),
    [categories.data, categorySlug],
  )
  const current = path[path.length - 1]
  // The search filters by category id: wait for the tree when the URL names a category.
  const categoryReady = !categorySlug || Boolean(current)
  const search = useSearch(toSearchParams(filters, current?.id), { enabled: categoryReady })

  if (categorySlug && categories.isSuccess && path.length === 0) {
    return <NotFoundPage title={t('catalog.notFound')} />
  }

  const setFilters = (next: CatalogFilters) => navigate(catalogHref(categorySlug, next))
  // A different category keeps the query, price and stock filters; attributes belong to a
  // category (shoe sizes mean nothing for phones), so they are dropped.
  const categoryHref = (slug: string | undefined) =>
    catalogHref(slug, withFilters(filters, { attrs: {} }))

  const heading = filters.q
    ? t('catalog.searchTitle', { q: filters.q })
    : (current?.name ?? t('catalog.allProducts'))
  const data = search.data
  const pageCount = data ? Math.ceil(data.total / data.page_size) : 0
  const filterCount = activeFilterCount(filters)
  const loadingFirst = !categoryReady || search.isPending

  const panel = categories.isError ? (
    <QueryError
      error={categories.error}
      onRetry={() => void categories.refetch()}
      retrying={categories.isRefetching}
      className="px-3 py-6"
    />
  ) : search.isError && !data ? null : (
    // No facets without results: the error state in the list says what happened.
    <FilterPanel
      facets={categories.data ? data?.facets : undefined}
      filters={filters}
      onChange={setFilters}
      categories={categories.data ?? []}
      path={path}
      categoryHref={categoryHref}
      onNavigate={() => setDrawerOpen(false)}
    />
  )

  return (
    <div className="page-container flex flex-col gap-5 pt-5 sm:pt-6">
      <title>{`${heading} | ${t('common.brand')}`}</title>
      <Breadcrumbs
        items={
          categorySlug || filters.q
            ? [
                { label: t('catalog.title'), href: '/catalog' },
                ...path.map((c) => ({ label: c.name, href: `/catalog/${c.slug}` })),
              ]
            : [{ label: t('catalog.title') }]
        }
      />

      <div className="flex min-w-0 flex-col gap-1">
        {categorySlug && !filters.q && categories.isPending ? (
          <Skeleton className="h-9 w-48" />
        ) : (
          <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text [overflow-wrap:anywhere] sm:text-3xl">
            {heading}
          </h1>
        )}
        {data ? (
          <p className="text-sm text-text-muted tabular" aria-live="polite">
            {t('common.productsCount', { count: data.total })}
          </p>
        ) : search.isError ? null : (
          <Skeleton className="h-5 w-28" />
        )}
      </div>

      <div className="lg:grid lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-8">
        <aside className="hidden lg:block" aria-label={t('catalog.filters')}>
          <div className="sticky top-36 max-h-[calc(100dvh-10rem)] overflow-y-auto pr-1 pb-6">
            {panel}
          </div>
        </aside>

        <div className="flex min-w-0 flex-col gap-4">
          <div className="flex items-center justify-between gap-3">
            <Button
              variant="secondary"
              className="lg:hidden"
              onClick={() => setDrawerOpen(true)}
              leadingIcon={<SlidersHorizontal aria-hidden="true" size={18} strokeWidth={1.75} />}
            >
              {filterCount > 0
                ? t('catalog.filtersWithCount', { count: filterCount })
                : t('catalog.filters')}
            </Button>
            <SortSelect
              value={effectiveSort(filters)}
              withRelevance={Boolean(filters.q)}
              onChange={(sort) => setFilters(withFilters(filters, { sort }))}
            />
          </div>

          <ActiveFilters
            filters={filters}
            onChange={setFilters}
            clearSearchHref={catalogHref(categorySlug, withFilters(filters, { q: '' }))}
          />

          {loadingFirst && !search.isError ? (
            <ProductGrid loading skeletonCount={12} />
          ) : search.isError ? (
            <SearchError
              error={search.error}
              onRetry={() => void search.refetch()}
              retrying={search.isRefetching}
            />
          ) : !data || data.items.length === 0 ? (
            <NoResults
              filters={filters}
              onClearFilters={() => setFilters(clearFilters(filters))}
              clearSearchHref={catalogHref(categorySlug, withFilters(filters, { q: '' }))}
            />
          ) : (
            <div
              className={
                search.isPlaceholderData ? 'opacity-60 transition-opacity duration-150' : undefined
              }
              aria-busy={search.isPlaceholderData || undefined}
            >
              <ProductGrid items={data.items} />
            </div>
          )}

          <Pagination
            page={filters.page}
            pageCount={pageCount}
            hrefFor={(page) => catalogHref(categorySlug, { ...filters, page })}
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
        title={t('catalog.filters')}
        closeLabel={t('common.close')}
        side="left"
        footer={
          <Button className="w-full" onClick={() => setDrawerOpen(false)}>
            {t('catalog.showResults', { count: data?.total ?? 0 })}
          </Button>
        }
      >
        {panel}
      </Drawer>
    </div>
  )
}

function SortSelect({
  value,
  withRelevance,
  onChange,
}: {
  value: SearchSort
  withRelevance: boolean
  onChange: (sort: SearchSort) => void
}) {
  const { t } = useTranslation()
  const options = SORTS.filter((sort) => withRelevance || sort !== 'relevance')
  return (
    <label className="ml-auto flex min-w-0 items-center gap-2 text-sm text-text-muted">
      <span className="hidden sm:inline">{t('catalog.sort')}</span>
      <span className="relative min-w-0">
        <select
          value={value}
          aria-label={t('catalog.sort')}
          onChange={(event) => onChange(event.target.value as SearchSort)}
          className="h-11 w-full max-w-48 min-w-0 cursor-pointer appearance-none truncate rounded-lg border border-border bg-surface pr-9 pl-3 text-sm font-medium text-text transition-colors duration-150 ease-out hover:border-border-strong focus-ring"
        >
          {options.map((sort) => (
            <option key={sort} value={sort}>
              {t(`catalog.sorts.${sort}`)}
            </option>
          ))}
        </select>
        <ChevronDown
          aria-hidden="true"
          size={18}
          strokeWidth={1.75}
          className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-text-muted"
        />
      </span>
    </label>
  )
}

type Chip = { key: string; label: string; next: CatalogFilters }

function ActiveFilters({
  filters,
  onChange,
  clearSearchHref,
}: {
  filters: CatalogFilters
  onChange: (next: CatalogFilters) => void
  clearSearchHref: string
}) {
  const { t } = useTranslation()
  const chips: Chip[] = []
  if (filters.priceMin !== null || filters.priceMax !== null) {
    chips.push({
      key: 'price',
      label: priceRangeLabel(t, filters.priceMin, filters.priceMax),
      next: withFilters(filters, { priceMin: null, priceMax: null }),
    })
  }
  if (filters.inStock) {
    chips.push({
      key: 'stock',
      label: t('catalog.inStockOnly'),
      next: withFilters(filters, { inStock: false }),
    })
  }
  for (const [code, values] of Object.entries(filters.attrs)) {
    for (const value of values) {
      chips.push({
        key: `${code}:${value}`,
        label: `${attributeLabel(t, code)}: ${valueLabel(value)}`,
        next: toggleAttr(filters, code, value),
      })
    }
  }
  if (!filters.q && chips.length === 0) return null

  const chipClass =
    'inline-flex h-9 max-w-full items-center gap-1 rounded-full bg-primary-soft pr-1 pl-3 text-sm font-medium text-primary'
  const removeClass =
    'grid size-7 shrink-0 place-items-center rounded-full hover:bg-surface focus-ring'

  return (
    <ul aria-label={t('catalog.activeFilters')} className="flex flex-wrap items-center gap-2">
      {filters.q && (
        <li className="max-w-full">
          <span className={chipClass}>
            <span className="truncate">{t('catalog.searchFor', { q: filters.q })}</span>
            <Link
              to={clearSearchHref}
              aria-label={t('catalog.clearSearch')}
              className={removeClass}
            >
              <X aria-hidden="true" size={16} strokeWidth={1.75} />
            </Link>
          </span>
        </li>
      )}
      {chips.map((chip) => (
        <li key={chip.key} className="max-w-full">
          <span className={chipClass}>
            <span className="truncate">{chip.label}</span>
            <button
              type="button"
              aria-label={t('catalog.removeFilter', { label: chip.label })}
              onClick={() => onChange(chip.next)}
              className={removeClass}
            >
              <X aria-hidden="true" size={16} strokeWidth={1.75} />
            </button>
          </span>
        </li>
      ))}
      {chips.length > 1 && (
        <li>
          <button
            type="button"
            onClick={() => onChange(clearFilters(filters))}
            className="h-9 rounded-full px-3 text-sm font-semibold text-text-muted hover:bg-surface-2 hover:text-text focus-ring"
          >
            {t('catalog.clearFilters')}
          </button>
        </li>
      )}
    </ul>
  )
}

function NoResults({
  filters,
  onClearFilters,
  clearSearchHref,
}: {
  filters: CatalogFilters
  onClearFilters: () => void
  clearSearchHref: string
}) {
  const { t } = useTranslation()
  if (hasFilters(filters)) {
    return (
      <EmptyState
        icon={<SearchX size={22} strokeWidth={1.75} />}
        title={t('catalog.filteredEmpty')}
        description={t('catalog.filteredEmptyHint')}
        action={
          <Button variant="secondary" onClick={onClearFilters}>
            {t('catalog.clearFilters')}
          </Button>
        }
      />
    )
  }
  if (filters.q) {
    return (
      <EmptyState
        icon={<SearchX size={22} strokeWidth={1.75} />}
        title={t('catalog.searchEmpty', { q: filters.q })}
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
    )
  }
  return (
    <EmptyState
      icon={<PackageOpen size={22} strokeWidth={1.75} />}
      title={t('catalog.empty')}
      description={t('catalog.emptyHint')}
    />
  )
}
