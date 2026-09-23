import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '../lib/cn'
import { DefaultLink, type LinkComponent } from '../lib/link'

export type PaginationProps = {
  page: number
  pageCount: number
  /** Builds the URL for a page so every page is a real, shareable link. */
  hrefFor: (page: number) => string
  linkAs?: LinkComponent
  labels: {
    nav: string
    previous: string
    next: string
    page: (page: number) => string
  }
  className?: string
}

/** Page numbers to show: always first/last, current +-1, gaps as null. */
export function pageWindow(page: number, pageCount: number): Array<number | null> {
  if (pageCount <= 7) return Array.from({ length: pageCount }, (_, i) => i + 1)
  const pages = new Set([1, pageCount, page - 1, page, page + 1])
  const sorted = [...pages].filter((p) => p >= 1 && p <= pageCount).sort((a, b) => a - b)
  const result: Array<number | null> = []
  sorted.forEach((p, i) => {
    const previous = sorted[i - 1]
    if (previous !== undefined && p - previous > 1) result.push(null)
    result.push(p)
  })
  return result
}

const itemClass =
  'grid h-10 min-w-10 place-items-center rounded-lg px-2 text-sm font-semibold tabular transition-colors duration-150 ease-out focus-ring'

export function Pagination({
  page,
  pageCount,
  hrefFor,
  linkAs: LinkAs = DefaultLink,
  labels,
  className,
}: PaginationProps) {
  if (pageCount <= 1) return null

  return (
    <nav aria-label={labels.nav} className={cn('flex justify-center', className)}>
      <ul className="flex flex-wrap items-center justify-center gap-1">
        <li>
          {page > 1 ? (
            <LinkAs
              href={hrefFor(page - 1)}
              className={cn(itemClass, 'text-text hover:bg-surface-2')}
            >
              <ChevronLeft aria-hidden="true" size={20} strokeWidth={1.75} />
              <span className="sr-only">{labels.previous}</span>
            </LinkAs>
          ) : (
            <span className={cn(itemClass, 'text-text-muted opacity-50')} aria-hidden="true">
              <ChevronLeft size={20} strokeWidth={1.75} />
            </span>
          )}
        </li>
        {pageWindow(page, pageCount).map((p, i) => (
          <li key={p ?? `gap-${i}`}>
            {p === null ? (
              <span className={cn(itemClass, 'text-text-muted')} aria-hidden="true">
                ...
              </span>
            ) : p === page ? (
              <span
                aria-current="page"
                aria-label={labels.page(p)}
                className={cn(itemClass, 'bg-primary text-primary-fg')}
              >
                {p}
              </span>
            ) : (
              <LinkAs href={hrefFor(p)} className={cn(itemClass, 'text-text hover:bg-surface-2')}>
                <span className="sr-only">{labels.page(p)}</span>
                <span aria-hidden="true">{p}</span>
              </LinkAs>
            )}
          </li>
        ))}
        <li>
          {page < pageCount ? (
            <LinkAs
              href={hrefFor(page + 1)}
              className={cn(itemClass, 'text-text hover:bg-surface-2')}
            >
              <ChevronRight aria-hidden="true" size={20} strokeWidth={1.75} />
              <span className="sr-only">{labels.next}</span>
            </LinkAs>
          ) : (
            <span className={cn(itemClass, 'text-text-muted opacity-50')} aria-hidden="true">
              <ChevronRight size={20} strokeWidth={1.75} />
            </span>
          )}
        </li>
      </ul>
    </nav>
  )
}
