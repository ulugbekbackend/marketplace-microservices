import { useMe, useSellerApplication } from '@bozorcha/api-client'
import { Badge, cn, Drawer, formatE164, Skeleton, Wordmark } from '@bozorcha/ui'
import { ClipboardList, LayoutDashboard, Menu, Package, Store, Wallet } from 'lucide-react'
import { useState, type ComponentType } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, NavLink, Outlet } from 'react-router'
import { LogoutButton } from './LogoutButton'
import { ThemeToggle } from './ThemeToggle'

type NavItem = {
  to: string
  labelKey: 'nav.dashboard' | 'nav.products' | 'nav.orders' | 'nav.payouts'
  icon: ComponentType<{ size?: number; strokeWidth?: number; 'aria-hidden'?: boolean }>
  end?: boolean
  soon?: boolean
}

const NAV: NavItem[] = [
  { to: '/', labelKey: 'nav.dashboard', icon: LayoutDashboard, end: true },
  { to: '/products', labelKey: 'nav.products', icon: Package },
  { to: '/orders', labelKey: 'nav.orders', icon: ClipboardList },
  { to: '/payouts', labelKey: 'nav.payouts', icon: Wallet, soon: true },
]

const itemBase =
  'flex h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors duration-150 ease-out'

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation()
  return (
    <ul className="flex flex-col gap-1">
      {NAV.map(({ to, labelKey, icon: Icon, end, soon }) => (
        <li key={to}>
          {soon ? (
            <span
              aria-disabled="true"
              className={cn(itemBase, 'cursor-not-allowed text-text-muted')}
            >
              <Icon aria-hidden size={20} strokeWidth={1.75} />
              <span className="flex-1">{t(labelKey)}</span>
              <Badge tone="muted">{t('nav.soon')}</Badge>
            </span>
          ) : (
            <NavLink
              to={to}
              end={end}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  itemBase,
                  'focus-ring',
                  isActive
                    ? 'bg-primary-soft font-semibold text-primary'
                    : 'text-text hover:bg-surface-2',
                )
              }
            >
              <Icon aria-hidden size={20} strokeWidth={1.75} />
              {t(labelKey)}
            </NavLink>
          )}
        </li>
      ))}
    </ul>
  )
}

/** Shop name from the approved application, and the signed-in phone. */
function ShopIdentity({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation()
  const me = useMe()
  const application = useSellerApplication()
  if (me.isPending || application.isPending) {
    return (
      <div className="flex flex-col gap-1.5" aria-hidden="true">
        <Skeleton className="h-4 w-28" />
        {!compact && <Skeleton className="h-3 w-24" />}
      </div>
    )
  }
  const shopName = application.data?.shop_name ?? t('header.shopFallback')
  return (
    <div className="flex min-w-0 flex-col">
      <span className="truncate text-sm font-semibold text-text">{shopName}</span>
      {me.data && (
        <span
          className={cn('truncate text-xs text-text-muted tabular', compact && 'hidden sm:block')}
        >
          {formatE164(me.data.phone)}
        </span>
      )}
    </div>
  )
}

function Brand() {
  const { t } = useTranslation()
  return (
    <Link
      to="/"
      className="flex items-baseline gap-2 rounded-lg focus-ring"
      aria-label={t('common.panel')}
    >
      <Wordmark className="text-xl" />
      <span className="text-sm font-semibold text-text-muted">{t('common.seller')}</span>
    </Link>
  )
}

/** Sidebar on desktop, drawer below `lg`; top bar with shop, theme and logout. */
export function PanelLayout() {
  const { t } = useTranslation()
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-border bg-surface lg:flex">
        <div aria-hidden="true" className="awning h-1 w-full" />
        <div className="px-5 pt-5 pb-6">
          <Brand />
        </div>
        <nav aria-label={t('nav.main')} className="flex-1 overflow-y-auto px-3">
          <NavList />
        </nav>
        <div className="flex items-center gap-3 border-t border-border px-5 py-4">
          <span
            aria-hidden="true"
            className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary-soft text-primary"
          >
            <Store size={18} strokeWidth={1.75} />
          </span>
          <ShopIdentity />
        </div>
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur-sm">
          <div aria-hidden="true" className="awning h-1 w-full lg:hidden" />
          <div className="flex h-16 items-center gap-2 px-3 sm:px-6">
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-label={t('nav.openMenu')}
              aria-expanded={menuOpen}
              className="grid size-11 shrink-0 place-items-center rounded-lg text-text hover:bg-surface-2 focus-ring lg:hidden"
            >
              <Menu aria-hidden="true" size={20} strokeWidth={1.75} />
            </button>
            <div className="min-w-0 lg:hidden">
              <Brand />
            </div>
            <div className="hidden min-w-0 lg:block">
              <ShopIdentity compact />
            </div>
            <div className="ml-auto flex items-center gap-1">
              <ThemeToggle />
              <LogoutButton />
            </div>
          </div>
        </header>
        <main id="main" tabIndex={-1} className="flex-1 outline-none">
          <Outlet />
        </main>
      </div>

      <Drawer
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        title={t('nav.menu')}
        side="left"
        closeLabel={t('common.close')}
        footer={<ShopIdentity />}
      >
        <nav aria-label={t('nav.main')}>
          <NavList onNavigate={() => setMenuOpen(false)} />
        </nav>
      </Drawer>
    </div>
  )
}
