import type { Category } from '@bozorcha/api-client'
import { cn, Skeleton } from '@bozorcha/ui'
import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

type CategoryTreeProps = {
  categories: Category[]
  activeSlug?: string
  /** Slugs from the root to the active category; those branches start expanded. */
  activePath: string[]
  /** Called after a link is followed (closes the mobile drawer). */
  onNavigate?: () => void
}

export function CategoryTree({
  categories,
  activeSlug,
  activePath,
  onNavigate,
}: CategoryTreeProps) {
  const { t } = useTranslation()
  return (
    <nav aria-label={t('catalog.categories')}>
      <ul className="flex flex-col gap-0.5">
        <li>
          <TreeLink
            href="/catalog"
            label={t('catalog.allProducts')}
            active={!activeSlug}
            onNavigate={onNavigate}
          />
        </li>
        {categories.map((category) => (
          <TreeNode
            key={category.id}
            category={category}
            depth={0}
            activeSlug={activeSlug}
            activePath={activePath}
            onNavigate={onNavigate}
          />
        ))}
      </ul>
    </nav>
  )
}

function TreeNode({
  category,
  depth,
  activeSlug,
  activePath,
  onNavigate,
}: {
  category: Category
  depth: number
  activeSlug?: string
  activePath: string[]
  onNavigate?: () => void
}) {
  const { t } = useTranslation()
  const hasChildren = category.children.length > 0
  const [expanded, setExpanded] = useState(() => activePath.includes(category.slug))
  const listId = `cat-${category.id}`

  return (
    <li>
      <div className="flex items-center gap-0.5" style={{ paddingLeft: depth * 12 }}>
        <TreeLink
          href={`/catalog/${category.slug}`}
          label={category.name}
          active={category.slug === activeSlug}
          onNavigate={onNavigate}
        />
        {hasChildren && (
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={listId}
            aria-label={t(expanded ? 'catalog.collapse' : 'catalog.expand', {
              name: category.name,
            })}
            onClick={() => setExpanded((value) => !value)}
            className="grid size-9 shrink-0 place-items-center rounded-lg text-text-muted hover:bg-surface-2 hover:text-text focus-ring"
          >
            <ChevronDown
              aria-hidden="true"
              size={18}
              strokeWidth={1.75}
              className={cn('transition-transform duration-150 ease-out', expanded && 'rotate-180')}
            />
          </button>
        )}
      </div>
      {hasChildren && (
        <ul id={listId} hidden={!expanded} className="mt-0.5 flex flex-col gap-0.5">
          {category.children.map((child) => (
            <TreeNode
              key={child.id}
              category={child}
              depth={depth + 1}
              activeSlug={activeSlug}
              activePath={activePath}
              onNavigate={onNavigate}
            />
          ))}
        </ul>
      )}
    </li>
  )
}

function TreeLink({
  href,
  label,
  active,
  onNavigate,
}: {
  href: string
  label: string
  active: boolean
  onNavigate?: () => void
}) {
  return (
    <Link
      to={href}
      onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'flex min-h-9 min-w-0 flex-1 items-center rounded-lg px-3 py-1.5 text-sm transition-colors duration-150 ease-out focus-ring',
        active ? 'bg-primary-soft font-semibold text-primary' : 'text-text hover:bg-surface-2',
      )}
    >
      <span className="truncate">{label}</span>
    </Link>
  )
}

export function CategoryTreeSkeleton() {
  return (
    <div className="flex flex-col gap-2" aria-hidden="true">
      {Array.from({ length: 7 }, (_, i) => (
        <Skeleton key={i} className="h-8" style={{ width: `${90 - (i % 3) * 15}%` }} />
      ))}
    </div>
  )
}
