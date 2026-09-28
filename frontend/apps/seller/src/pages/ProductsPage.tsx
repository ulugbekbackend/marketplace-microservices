import {
  useSellerProductDetails,
  useSellerProducts,
  type ProductStatus,
  type SellerProduct,
  type SellerProductDetail,
} from '@bozorcha/api-client'
import {
  Button,
  DataTable,
  EmptyState,
  formatPrice,
  Input,
  Pagination,
  Skeleton,
  Tabs,
  type DataTableColumn,
} from '@bozorcha/ui'
import { ImageOff, PackageOpen, Plus, Search, SearchX } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import { ProductStatusBadge } from '../components/ProductStatusBadge'
import { QueryError } from '../components/QueryError'
import { RouterLink } from '../components/RouterLink'
import { VariantsPanel } from '../components/VariantsPanel'

export const PAGE_SIZE = 20
export const SEARCH_DEBOUNCE_MS = 300

const FILTERS = ['all', 'draft', 'active', 'archived'] as const
type Filter = (typeof FILTERS)[number]

const isFilter = (value: string | null): value is Filter => FILTERS.includes(value as Filter)

/** Totals across a product's variants; null while its details load. */
function stockTotals(detail: SellerProductDetail | undefined) {
  if (!detail) return null
  return detail.variants.reduce(
    (sum, variant) => ({
      stock: sum.stock + (variant.stock ?? 0),
      reserved: sum.reserved + (variant.reserved ?? 0),
    }),
    { stock: 0, reserved: 0 },
  )
}

function priceRange(product: SellerProduct): string | null {
  const { min_price_tiyin: min, max_price_tiyin: max } = product
  if (min === null || max === null) return null
  return min === max ? formatPrice(min) : `${formatPrice(min)} – ${formatPrice(max)}`
}

export function ProductsPage() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const filter: Filter = isFilter(params.get('status')) ? (params.get('status') as Filter) : 'all'
  const page = Math.max(1, Number(params.get('page')) || 1)
  const [search, setSearch] = useState(q)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // Debounced search: the URL (and the query) follow the input 300 ms after typing stops.
  useEffect(() => {
    if (search.trim() === q) return
    const timer = window.setTimeout(() => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current)
          if (search.trim()) next.set('q', search.trim())
          else next.delete('q')
          next.delete('page')
          return next
        },
        { replace: true },
      )
    }, SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [search, q, setParams])

  const products = useSellerProducts({
    q: q || undefined,
    status: filter === 'all' ? undefined : (filter as ProductStatus),
    page,
    page_size: PAGE_SIZE,
  })
  const items = products.data?.items
  const ids = useMemo(() => items?.map((item) => item.id) ?? [], [items])
  const details = useSellerProductDetails(ids)
  const detailById = new Map(ids.map((id, index) => [id, details[index]?.data]))

  const setFilter = (value: string) => {
    setParams((current) => {
      const next = new URLSearchParams(current)
      if (value === 'all') next.delete('status')
      else next.set('status', value)
      next.delete('page')
      return next
    })
  }

  const hrefFor = (target: number) => {
    const next = new URLSearchParams(params)
    if (target === 1) next.delete('page')
    else next.set('page', String(target))
    const query = next.toString()
    return `/products${query ? `?${query}` : ''}`
  }

  const toggle = (id: string) =>
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const columns: DataTableColumn<SellerProduct>[] = [
    {
      id: 'image',
      header: t('products.image'),
      hideHeader: true,
      className: 'w-14 pr-0',
      skeleton: <Skeleton className="size-11" />,
      cell: (product) =>
        product.image_url ? (
          <img
            src={product.image_url}
            alt=""
            loading="lazy"
            className="size-11 rounded-lg border border-border object-cover"
          />
        ) : (
          <span
            aria-hidden="true"
            className="grid size-11 place-items-center rounded-lg bg-surface-2 text-text-muted"
          >
            <ImageOff size={18} strokeWidth={1.75} />
          </span>
        ),
    },
    {
      id: 'title',
      header: t('products.title'),
      className: 'min-w-0',
      cell: (product) => (
        <div className="flex min-w-0 flex-col gap-0.5">
          <Link
            to={`/products/${product.id}`}
            className="line-clamp-2 rounded-sm font-semibold break-words text-text hover:text-primary hover:underline focus-ring"
          >
            {product.title}
          </Link>
          <span className="text-xs text-text-muted">{product.category.name}</span>
          <span className="mt-1 flex flex-wrap items-center gap-2 sm:hidden">
            <ProductStatusBadge status={product.status} />
            <span className="text-xs text-text tabular">{priceRange(product) ?? '—'}</span>
          </span>
        </div>
      ),
    },
    {
      id: 'status',
      header: t('products.status'),
      className: 'hidden sm:table-cell',
      cell: (product) => <ProductStatusBadge status={product.status} />,
    },
    {
      id: 'variants',
      header: t('products.variants'),
      align: 'end',
      className: 'hidden md:table-cell tabular',
      cell: (product) => product.variants_count,
    },
    {
      id: 'price',
      header: t('products.price'),
      align: 'end',
      className: 'hidden sm:table-cell tabular whitespace-nowrap',
      cell: (product) => priceRange(product) ?? <span className="text-text-muted">—</span>,
    },
    {
      id: 'stock',
      header: t('products.stockReserved'),
      align: 'end',
      className: 'hidden lg:table-cell tabular whitespace-nowrap',
      cell: (product) => {
        const totals = stockTotals(detailById.get(product.id))
        if (!totals) return <Skeleton className="ml-auto h-4 w-16" />
        return (
          <span>
            {t('products.units', { count: totals.stock })}
            <span className="text-text-muted">
              {' '}
              / {t('products.reservedUnits', { count: totals.reserved })}
            </span>
          </span>
        )
      },
    },
  ]

  const filtered = Boolean(q) || filter !== 'all'
  const emptyState = filtered ? (
    <EmptyState
      icon={<SearchX size={22} strokeWidth={1.75} />}
      title={t('products.notFound')}
      description={t('products.notFoundHint')}
      action={
        <Button
          variant="secondary"
          onClick={() => {
            setSearch('')
            setParams(new URLSearchParams())
          }}
        >
          {t('products.clearFilters')}
        </Button>
      }
    />
  ) : (
    <EmptyState
      icon={<PackageOpen size={22} strokeWidth={1.75} />}
      title={t('products.empty')}
      description={t('products.emptyHint')}
      action={<NewProductLink />}
    />
  )

  const total = products.data?.total ?? 0
  const pageCount = Math.ceil(total / (products.data?.page_size ?? PAGE_SIZE))

  const listing = products.isError ? (
    <QueryError
      error={products.error}
      onRetry={() => void products.refetch()}
      retrying={products.isFetching}
    />
  ) : (
    <div className="flex flex-col gap-4">
      <DataTable
        caption={t('products.tableCaption')}
        columns={columns}
        rows={items}
        getRowId={(product) => product.id}
        loading={products.isPending}
        stale={products.isPlaceholderData}
        empty={emptyState}
        renderExpanded={(product) => <VariantsPanel productId={product.id} title={product.title} />}
        expandedIds={expanded}
        onToggleExpanded={toggle}
        expandLabel={(product) => t('products.showVariants', { title: product.title })}
      />
      <Pagination
        page={page}
        pageCount={pageCount}
        hrefFor={hrefFor}
        linkAs={RouterLink}
        labels={{
          nav: t('pagination.nav'),
          previous: t('pagination.previous'),
          next: t('pagination.next'),
          page: (n) => t('pagination.page', { page: n }),
        }}
      />
    </div>
  )

  return (
    <div className="page-container flex flex-col gap-5 py-6 sm:py-8">
      <title>{`${t('products.pageTitle')} | ${t('common.panel')}`}</title>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text sm:text-3xl">
            {t('products.pageTitle')}
          </h1>
          {products.data && (
            <p className="mt-1 text-sm text-text-muted tabular">
              {t('products.total', { count: total })}
            </p>
          )}
        </div>
        <NewProductLink />
      </div>

      <form role="search" onSubmit={(event) => event.preventDefault()} className="max-w-md">
        <Input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          aria-label={t('products.searchLabel')}
          placeholder={t('products.searchPlaceholder')}
          prefix={<Search aria-hidden="true" size={18} strokeWidth={1.75} />}
        />
      </form>

      <Tabs
        label={t('products.filterLabel')}
        value={filter}
        onValueChange={setFilter}
        items={FILTERS.map((id) => ({
          id,
          label: id === 'all' ? t('products.filterAll') : t(`productStatus.${id}`),
          content: listing,
        }))}
      />
    </div>
  )
}

function NewProductLink() {
  const { t } = useTranslation()
  return (
    <Link
      to="/products/new"
      className="inline-flex h-11 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-primary-fg transition-colors duration-150 ease-out hover:bg-primary-hover focus-ring"
    >
      <Plus aria-hidden="true" size={18} strokeWidth={2} />
      {t('products.new')}
    </Link>
  )
}
