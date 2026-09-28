import { ChevronRight } from 'lucide-react'
import { Fragment, useId, type ReactNode } from 'react'
import { cn } from '../lib/cn'
import { Skeleton } from './Skeleton'

export type DataTableColumn<T> = {
  id: string
  header: ReactNode
  cell: (row: T) => ReactNode
  /** Applied to the header and every cell, e.g. `hidden md:table-cell` to drop a column on phones. */
  className?: string
  align?: 'start' | 'end' | 'center'
  /** Keeps the header for screen readers but hides it visually (e.g. an image column). */
  hideHeader?: boolean
  /** Skeleton shape while loading; defaults to a text line. */
  skeleton?: ReactNode
}

export type DataTableProps<T> = {
  columns: DataTableColumn<T>[]
  rows: T[] | undefined
  getRowId: (row: T) => string
  /** Accessible table name (rendered as a visually hidden caption). */
  caption: string
  loading?: boolean
  skeletonRows?: number
  /** Shown instead of the body when `rows` is empty. */
  empty?: ReactNode
  /** Dims the table while newer data loads (e.g. the next page). */
  stale?: boolean
  /** Makes rows expandable: a toggle column is added at the start. */
  renderExpanded?: (row: T) => ReactNode
  expandedIds?: ReadonlySet<string>
  onToggleExpanded?: (id: string) => void
  /** Accessible name of a row's expand button, e.g. "Variantlar: Atlas ko'ylak". */
  expandLabel?: (row: T) => string
  className?: string
}

const alignClass = { start: 'text-left', end: 'text-right', center: 'text-center' } as const

/**
 * Semantic table with loading skeleton, empty state and optional expandable rows. Wide tables
 * scroll inside their own frame, never the page.
 */
export function DataTable<T>({
  columns,
  rows,
  getRowId,
  caption,
  loading = false,
  skeletonRows = 5,
  empty,
  stale = false,
  renderExpanded,
  expandedIds,
  onToggleExpanded,
  expandLabel,
  className,
}: DataTableProps<T>) {
  const baseId = useId()
  const expandable = Boolean(renderExpanded)
  const columnCount = columns.length + (expandable ? 1 : 0)
  const showSkeleton = loading && !rows
  const isEmpty = !showSkeleton && rows !== undefined && rows.length === 0

  return (
    <div
      className={cn(
        'overflow-x-auto rounded-xl border border-border bg-surface',
        stale && 'opacity-60 transition-opacity duration-150',
        className,
      )}
    >
      <table className="w-full border-collapse text-sm" aria-busy={loading || stale || undefined}>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-border bg-surface-2 text-text-muted">
            {expandable && (
              <th scope="col" className="w-12 px-2 py-2.5">
                <span className="sr-only">{caption}</span>
              </th>
            )}
            {columns.map((column) => (
              <th
                key={column.id}
                scope="col"
                className={cn(
                  'px-3 py-2.5 text-xs font-semibold whitespace-nowrap',
                  alignClass[column.align ?? 'start'],
                  column.className,
                )}
              >
                {column.hideHeader ? (
                  <span className="sr-only">{column.header}</span>
                ) : (
                  column.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {showSkeleton &&
            Array.from({ length: skeletonRows }, (_, index) => (
              <tr key={index} className="border-b border-border last:border-0" aria-hidden="true">
                {expandable && (
                  <td className="px-2 py-3">
                    <Skeleton className="mx-auto size-6" />
                  </td>
                )}
                {columns.map((column) => (
                  <td key={column.id} className={cn('px-3 py-3', column.className)}>
                    {column.skeleton ?? <Skeleton className="h-4 w-full max-w-32" />}
                  </td>
                ))}
              </tr>
            ))}
          {isEmpty && (
            <tr>
              <td colSpan={columnCount} className="p-4">
                {empty}
              </td>
            </tr>
          )}
          {!showSkeleton &&
            rows?.map((row) => {
              const id = getRowId(row)
              const expanded = expandable && Boolean(expandedIds?.has(id))
              const panelId = `${baseId}-row-${id}`
              return (
                <Fragment key={id}>
                  <tr
                    data-state={expanded ? 'expanded' : undefined}
                    className={cn(
                      'border-b border-border align-middle transition-colors duration-150 last:border-0 hover:bg-surface-2/60',
                      expanded && 'border-b-0 bg-surface-2/60',
                    )}
                  >
                    {expandable && (
                      <td className="px-2 py-2">
                        <button
                          type="button"
                          aria-expanded={expanded}
                          aria-controls={expanded ? panelId : undefined}
                          aria-label={expandLabel?.(row) ?? id}
                          onClick={() => onToggleExpanded?.(id)}
                          className="grid size-9 place-items-center rounded-lg text-text-muted transition-colors duration-150 ease-out hover:bg-surface-2 hover:text-text focus-ring"
                        >
                          <ChevronRight
                            aria-hidden="true"
                            size={20}
                            strokeWidth={1.75}
                            className={cn(
                              'transition-transform duration-150 ease-out',
                              expanded && 'rotate-90',
                            )}
                          />
                        </button>
                      </td>
                    )}
                    {columns.map((column) => (
                      <td
                        key={column.id}
                        className={cn(
                          'px-3 py-2.5',
                          alignClass[column.align ?? 'start'],
                          column.className,
                        )}
                      >
                        {column.cell(row)}
                      </td>
                    ))}
                  </tr>
                  {expanded && renderExpanded && (
                    <tr
                      id={panelId}
                      className="border-b border-border bg-surface-2/60 last:border-0"
                    >
                      <td colSpan={columnCount} className="px-2 pt-0 pb-3 sm:px-4">
                        {renderExpanded(row)}
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
        </tbody>
      </table>
    </div>
  )
}
