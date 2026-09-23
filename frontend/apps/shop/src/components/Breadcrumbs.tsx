import { ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

export type Crumb = { label: string; href?: string }

/** Trail of links; the last crumb is the current page. */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  const { t } = useTranslation()
  const all: Crumb[] = [{ label: t('common.home'), href: '/' }, ...items]
  return (
    <nav aria-label={t('common.breadcrumb')} className="min-w-0 text-sm">
      <ol className="flex flex-wrap items-center gap-x-1 gap-y-0.5 text-text-muted">
        {all.map((crumb, index) => {
          const last = index === all.length - 1
          return (
            <li
              key={`${crumb.label}-${index}`}
              className="flex max-w-full min-w-0 items-center gap-1"
            >
              {index > 0 && (
                <ChevronRight
                  aria-hidden="true"
                  size={14}
                  strokeWidth={1.75}
                  className="shrink-0"
                />
              )}
              {crumb.href && !last ? (
                <Link
                  to={crumb.href}
                  className="truncate rounded-sm hover:text-text hover:underline focus-ring"
                >
                  {crumb.label}
                </Link>
              ) : (
                <span aria-current={last ? 'page' : undefined} className="truncate text-text">
                  {crumb.label}
                </span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
