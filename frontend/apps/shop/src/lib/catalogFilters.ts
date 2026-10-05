import type { PriceRangeFacet, SearchParams, SearchSort } from '@bozorcha/api-client'

/**
 * Catalog listing state, kept in the URL so a filtered page can be shared, reloaded and
 * navigated with the back button. The category lives in the path (`/catalog/<slug>`); the rest
 * is the query string, with the API's own names:
 *
 *   ?q=futbolka&sort=price_asc&price_min=10000000&price_max=49999999&in_stock=1
 *   &attr[color]=qizil&attr[color]=qora&page=2
 *
 * Defaults are left out of the URL, so equal filters always produce the same address.
 */
export type CatalogFilters = {
  q: string
  page: number
  /** null = the default order (relevance with a query, newest without). */
  sort: SearchSort | null
  /** Tiyin, inclusive. */
  priceMin: number | null
  /** Tiyin, inclusive. */
  priceMax: number | null
  inStock: boolean
  /** Attribute code -> selected values. */
  attrs: Record<string, string[]>
}

export const CATALOG_PAGE_SIZE = 24

export const SORTS = [
  'relevance',
  'newest',
  'price_asc',
  'price_desc',
] as const satisfies readonly SearchSort[]

const ATTR_KEY = /^attr\[([^\]]+)\]$/

const parseTiyin = (value: string | null): number | null => {
  if (value === null || !/^\d{1,15}$/.test(value)) return null
  return Number(value)
}

export function parseCatalogParams(params: URLSearchParams): CatalogFilters {
  const page = Number.parseInt(params.get('page') ?? '', 10)
  const sort = SORTS.find((s) => s === params.get('sort')) ?? null
  const attrs: Record<string, string[]> = {}
  for (const key of new Set(params.keys())) {
    const code = ATTR_KEY.exec(key)?.[1]
    if (!code) continue
    const values = [...new Set(params.getAll(key).filter(Boolean))]
    if (values.length > 0) attrs[code] = values
  }
  return {
    q: params.get('q')?.trim() ?? '',
    page: Number.isFinite(page) && page > 0 ? page : 1,
    sort,
    priceMin: parseTiyin(params.get('price_min')),
    priceMax: parseTiyin(params.get('price_max')),
    inStock: params.get('in_stock') === '1' || params.get('in_stock') === 'true',
    attrs,
  }
}

/** The canonical query string: fixed key order, sorted attribute codes and values. */
export function toCatalogParams(filters: CatalogFilters): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.q) params.set('q', filters.q)
  const sort = effectiveSort(filters)
  if (sort !== defaultSort(filters.q)) params.set('sort', sort)
  if (filters.priceMin !== null) params.set('price_min', String(filters.priceMin))
  if (filters.priceMax !== null) params.set('price_max', String(filters.priceMax))
  if (filters.inStock) params.set('in_stock', '1')
  for (const code of Object.keys(filters.attrs).sort()) {
    for (const value of [...filters.attrs[code]!].sort()) params.append(`attr[${code}]`, value)
  }
  if (filters.page > 1) params.set('page', String(filters.page))
  return params
}

export const defaultSort = (q: string): SearchSort => (q ? 'relevance' : 'newest')

/** The order in use. "Relevance" without a query has nothing to rank by: newest instead. */
export function effectiveSort(filters: CatalogFilters): SearchSort {
  const sort = filters.sort ?? defaultSort(filters.q)
  return !filters.q && sort === 'relevance' ? 'newest' : sort
}

/** `/catalog[/<slug>][?query]` for the given filters. */
export function catalogHref(categorySlug: string | undefined, filters: CatalogFilters): string {
  const query = toCatalogParams(filters).toString()
  return `/catalog${categorySlug ? `/${categorySlug}` : ''}${query ? `?${query}` : ''}`
}

export function toSearchParams(
  filters: CatalogFilters,
  categoryId: string | undefined,
): SearchParams {
  return {
    q: filters.q || undefined,
    category: categoryId,
    price_min: filters.priceMin ?? undefined,
    price_max: filters.priceMax ?? undefined,
    in_stock: filters.inStock || undefined,
    attr: Object.keys(filters.attrs).length > 0 ? filters.attrs : undefined,
    sort: effectiveSort(filters),
    page: filters.page,
    page_size: CATALOG_PAGE_SIZE,
  }
}

/* ----------------------------------------------------------------- updates */

/** Every change of a filter starts again from page 1. */
export const withFilters = (
  filters: CatalogFilters,
  patch: Partial<Omit<CatalogFilters, 'page'>>,
): CatalogFilters => ({ ...filters, ...patch, page: 1 })

export function toggleAttr(filters: CatalogFilters, code: string, value: string): CatalogFilters {
  const current = filters.attrs[code] ?? []
  const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value]
  const attrs = { ...filters.attrs }
  if (next.length > 0) attrs[code] = next
  else delete attrs[code]
  return withFilters(filters, { attrs })
}

/**
 * The price filter of a facet bucket. Buckets have an exclusive upper bound while `price_max`
 * is inclusive, hence `to - 1`.
 */
export const bucketRange = (bucket: PriceRangeFacet) => ({
  priceMin: bucket.from_tiyin,
  priceMax: bucket.to_tiyin === null ? null : bucket.to_tiyin - 1,
})

export function isBucketSelected(bucket: PriceRangeFacet, filters: CatalogFilters): boolean {
  if (filters.priceMin === null && filters.priceMax === null) return false
  const range = bucketRange(bucket)
  return range.priceMin === filters.priceMin && range.priceMax === filters.priceMax
}

/** Everything except the query and the order (those are not "filters" to the customer). */
export function hasFilters(filters: CatalogFilters): boolean {
  return (
    filters.priceMin !== null ||
    filters.priceMax !== null ||
    filters.inStock ||
    Object.keys(filters.attrs).length > 0
  )
}

export function activeFilterCount(filters: CatalogFilters): number {
  const attrValues = Object.values(filters.attrs).reduce((sum, values) => sum + values.length, 0)
  const price = filters.priceMin !== null || filters.priceMax !== null ? 1 : 0
  return attrValues + price + (filters.inStock ? 1 : 0)
}

export const clearFilters = (filters: CatalogFilters): CatalogFilters =>
  withFilters(filters, { priceMin: null, priceMax: null, inStock: false, attrs: {} })
