import { useCart } from '@bozorcha/api-client'
import { cn } from '@bozorcha/ui'
import { ShoppingCart } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { NavLink } from 'react-router'

/** Header cart icon with the total quantity; the count is hidden while unknown or zero. */
export function CartLink() {
  const { t } = useTranslation()
  const { data } = useCart()
  const count = data?.items_count ?? 0
  const label = count > 0 ? t('header.cartWithCount', { count }) : t('header.cart')

  return (
    <NavLink
      to="/cart"
      aria-label={label}
      title={label}
      className={({ isActive }) =>
        cn(
          'relative grid size-11 shrink-0 place-items-center rounded-lg transition-colors duration-150 ease-out hover:bg-surface-2 focus-ring',
          isActive ? 'text-primary' : 'text-text',
        )
      }
    >
      <ShoppingCart aria-hidden="true" size={20} strokeWidth={1.75} />
      {count > 0 && (
        <span
          aria-hidden="true"
          data-testid="cart-count"
          className="absolute top-1 right-0.5 grid h-5 min-w-5 place-items-center rounded-full bg-accent px-1 text-[11px] leading-none font-bold text-accent-fg tabular ring-2 ring-surface"
        >
          {count > 99 ? '99+' : count}
        </span>
      )}
    </NavLink>
  )
}
