import { useCategories } from '@bozorcha/api-client'
import { cn, Wordmark } from '@bozorcha/ui'
import { useTranslation } from 'react-i18next'
import { Link, NavLink } from 'react-router'
import { AccountMenu } from './AccountMenu'
import { SearchBox } from './SearchBox'
import { ThemeToggle } from './ThemeToggle'

export function Header() {
  const { t } = useTranslation()
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-surface">
      {/* Striped market-stall awning: the brand's one decorative flourish. */}
      <div aria-hidden="true" className="awning h-1.5" />
      <div className="page-container flex h-16 items-center gap-3 md:gap-6">
        <Link
          to="/"
          className="shrink-0 rounded-md focus-ring"
          aria-label={`${t('common.brand')}, ${t('common.home')}`}
        >
          <Wordmark />
        </Link>
        <SearchBox className="hidden max-w-2xl md:flex" />
        <div className="ml-auto flex shrink-0 items-center gap-1">
          <ThemeToggle />
          <AccountMenu />
        </div>
      </div>
      <div className="page-container pb-3 md:hidden">
        <SearchBox />
      </div>
      <CategoryStrip />
    </header>
  )
}

/** Top-level categories under the header on tablet and up. */
function CategoryStrip() {
  const { t } = useTranslation()
  const { data } = useCategories()
  if (!data || data.length === 0) return null
  return (
    <nav aria-label={t('header.mainNav')} className="hidden border-t border-border md:block">
      <ul className="page-container flex h-11 items-center gap-1 overflow-x-auto [scrollbar-width:none]">
        {data.map((category) => (
          <li key={category.id} className="shrink-0">
            <NavLink
              to={`/catalog/${category.slug}`}
              className={({ isActive }) =>
                cn(
                  'inline-flex h-8 items-center rounded-full px-3 text-sm font-medium whitespace-nowrap transition-colors duration-150 ease-out focus-ring',
                  isActive
                    ? 'bg-primary-soft text-primary'
                    : 'text-text-muted hover:bg-surface-2 hover:text-text',
                )
              }
            >
              {category.name}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
