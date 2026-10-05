import type { AttributeFacet, Category, PriceRangeFacet, SearchFacets } from '@bozorcha/api-client'
import { Checkbox, cn, Skeleton } from '@bozorcha/ui'
import { ChevronLeft } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import {
  bucketRange,
  isBucketSelected,
  toggleAttr,
  withFilters,
  type CatalogFilters,
} from '../../lib/catalogFilters'
import { attributeLabel, priceBucketLabel, valueLabel } from '../../lib/searchLabels'

/** Values shown per attribute before "show more". */
const VISIBLE_VALUES = 6

type FilterPanelProps = {
  facets: SearchFacets | undefined
  filters: CatalogFilters
  onChange: (next: CatalogFilters) => void
  /** The category tree from the catalog (names, slugs, nesting). */
  categories: Category[]
  /** Root first, the current category last; empty for all products. */
  path: Category[]
  /** URL of a category (undefined = all products), keeping the query and other filters. */
  categoryHref: (slug: string | undefined) => string
  /** Called after a category link is followed (closes the mobile drawer). */
  onNavigate?: () => void
}

/** Facet filters of a listing: category drill-down, price buckets, stock and attributes. */
export function FilterPanel({
  facets,
  filters,
  onChange,
  categories,
  path,
  categoryHref,
  onNavigate,
}: FilterPanelProps) {
  const { t } = useTranslation()
  if (!facets) return <FilterPanelSkeleton />
  return (
    <div className="flex flex-col gap-6" data-testid="filter-panel">
      <CategoryFacet
        counts={new Map(facets.categories.map((c) => [c.id, c.count]))}
        categories={categories}
        path={path}
        categoryHref={categoryHref}
        onNavigate={onNavigate}
      />
      <PriceFacet buckets={facets.price_ranges} filters={filters} onChange={onChange} />
      <Section title={t('catalog.availability')}>
        <Checkbox
          label={t('catalog.inStockOnly')}
          checked={filters.inStock}
          onChange={(event) => onChange(withFilters(filters, { inStock: event.target.checked }))}
        />
      </Section>
      {facets.attributes.map((facet) => (
        <AttributeFilter key={facet.code} facet={facet} filters={filters} onChange={onChange} />
      ))}
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-2.5">
      <legend className="mb-2.5 font-heading text-sm font-bold text-text">{title}</legend>
      {children}
    </fieldset>
  )
}

const Count = ({ value }: { value: number }) => (
  <span className="ml-auto shrink-0 pl-2 text-xs text-text-muted tabular">{value}</span>
)

/* --------------------------------------------------------------- category */

function CategoryFacet({
  counts,
  categories,
  path,
  categoryHref,
  onNavigate,
}: {
  counts: Map<string, number>
  categories: Category[]
  path: Category[]
  categoryHref: (slug: string | undefined) => string
  onNavigate?: () => void
}) {
  const { t } = useTranslation()
  const current = path[path.length - 1]
  const parent = path[path.length - 2]
  const children = (current ? current.children : categories).filter(
    (c) => (counts.get(c.id) ?? 0) > 0,
  )
  if (!current && children.length === 0) return null

  const linkClass =
    'flex min-h-9 min-w-0 items-center rounded-lg px-2.5 py-1.5 text-sm transition-colors duration-150 ease-out focus-ring'

  return (
    <nav aria-label={t('catalog.category')} className="flex flex-col gap-1">
      <h2 className="mb-1.5 font-heading text-sm font-bold text-text">{t('catalog.category')}</h2>
      {current && (
        <Link
          to={categoryHref(parent?.slug)}
          onClick={onNavigate}
          className={cn(linkClass, 'gap-1 text-text-muted hover:bg-surface-2 hover:text-text')}
        >
          <ChevronLeft aria-hidden="true" size={16} strokeWidth={1.75} className="shrink-0" />
          <span className="truncate">{parent ? parent.name : t('catalog.allCategories')}</span>
        </Link>
      )}
      {current && (
        <p
          aria-current="page"
          className={cn(linkClass, 'bg-primary-soft font-semibold text-primary')}
        >
          <span className="truncate">{current.name}</span>
          <Count value={counts.get(current.id) ?? 0} />
        </p>
      )}
      {children.length > 0 && (
        <ul className={cn('flex flex-col gap-0.5', current && 'pl-3')}>
          {children.map((child) => (
            <li key={child.id}>
              <Link
                to={categoryHref(child.slug)}
                onClick={onNavigate}
                className={cn(linkClass, 'text-text hover:bg-surface-2')}
              >
                <span className="truncate">{child.name}</span>
                <Count value={counts.get(child.id) ?? 0} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </nav>
  )
}

/* ------------------------------------------------------------------ price */

function PriceFacet({
  buckets,
  filters,
  onChange,
}: {
  buckets: PriceRangeFacet[]
  filters: CatalogFilters
  onChange: (next: CatalogFilters) => void
}) {
  const { t } = useTranslation()
  const name = useId()
  if (buckets.length === 0) return null
  const anySelected = filters.priceMin === null && filters.priceMax === null
  return (
    <Section title={t('catalog.price')}>
      <Radio
        name={name}
        label={t('catalog.anyPrice')}
        checked={anySelected}
        onChange={() => onChange(withFilters(filters, { priceMin: null, priceMax: null }))}
      />
      {buckets.map((bucket) => {
        const selected = isBucketSelected(bucket, filters)
        return (
          <Radio
            key={bucket.key}
            name={name}
            label={priceBucketLabel(t, bucket)}
            count={bucket.count}
            checked={selected}
            disabled={bucket.count === 0 && !selected}
            onChange={() => onChange(withFilters(filters, bucketRange(bucket)))}
          />
        )
      })}
    </Section>
  )
}

function Radio({
  name,
  label,
  count,
  checked,
  disabled,
  onChange,
}: {
  name: string
  label: string
  count?: number
  checked: boolean
  disabled?: boolean
  onChange: () => void
}) {
  const id = useId()
  return (
    <div className={cn('flex items-center gap-3', disabled && 'opacity-50')}>
      <input
        id={id}
        type="radio"
        name={name}
        checked={checked}
        disabled={disabled}
        onChange={onChange}
        className={cn(
          'size-5 shrink-0 cursor-pointer appearance-none rounded-full border border-border-strong bg-surface',
          'transition-[border-color,border-width] duration-150 ease-out checked:border-[6px] checked:border-primary focus-ring',
          'disabled:cursor-not-allowed',
        )}
      />
      <label
        htmlFor={id}
        className={cn(
          'flex min-w-0 flex-1 items-center text-sm text-text tabular',
          disabled ? 'cursor-not-allowed' : 'cursor-pointer',
          checked && 'font-semibold',
        )}
      >
        <span className="min-w-0">{label}</span>
        {count !== undefined && <Count value={count} />}
      </label>
    </div>
  )
}

/* ------------------------------------------------------------- attributes */

function AttributeFilter({
  facet,
  filters,
  onChange,
}: {
  facet: AttributeFacet
  filters: CatalogFilters
  onChange: (next: CatalogFilters) => void
}) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const listId = useId()
  const selected = filters.attrs[facet.code] ?? []
  // Values still in the URL but no longer in the facet (zero hits) stay visible to be removed.
  const values = [
    ...facet.values,
    ...selected
      .filter((value) => !facet.values.some((v) => v.value === value))
      .map((value) => ({ value, count: 0, selected: true })),
  ]
  if (values.every((v) => v.count === 0 && !selected.includes(v.value))) return null
  const hidden = values.length - VISIBLE_VALUES
  const shown = expanded || hidden <= 0 ? values : values.slice(0, VISIBLE_VALUES)

  return (
    <Section title={attributeLabel(t, facet.code)}>
      <div id={listId} className="flex flex-col gap-2.5">
        {shown.map((option) => {
          const checked = selected.includes(option.value)
          return (
            <Checkbox
              key={option.value}
              checked={checked}
              disabled={option.count === 0 && !checked}
              onChange={() => onChange(toggleAttr(filters, facet.code, option.value))}
              label={
                <span className="flex min-w-0 items-center">
                  <span className="min-w-0 [overflow-wrap:anywhere]">
                    {valueLabel(option.value)}
                  </span>
                  <Count value={option.count} />
                </span>
              }
              className="[&_label]:flex-1 [&>span:last-child]:flex-1"
            />
          )
        })}
      </div>
      {hidden > 0 && (
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={listId}
          onClick={() => setExpanded((value) => !value)}
          className="self-start rounded-sm text-sm font-semibold text-primary hover:underline focus-ring"
        >
          {expanded ? t('catalog.showLess') : t('catalog.showMore', { count: hidden })}
        </button>
      )}
    </Section>
  )
}

export function FilterPanelSkeleton() {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-6" role="status" aria-label={t('common.loading')}>
      {[5, 4, 1, 5].map((rows, i) => (
        <div key={i} className="flex flex-col gap-2.5">
          <Skeleton className="h-4 w-24" />
          {Array.from({ length: rows }, (_, j) => (
            <Skeleton key={j} className="h-5" style={{ width: `${85 - ((i + j) % 3) * 15}%` }} />
          ))}
        </div>
      ))}
    </div>
  )
}
