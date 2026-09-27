import { useSession } from '@bozorcha/api-client'
import { EmptyState } from '@bozorcha/ui'
import { ClipboardList } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate } from 'react-router'

/** Placeholder until the order API exists: keeps the checkout route and its login gate. */
export function CheckoutPage() {
  const { t } = useTranslation()
  const { isAuthenticated } = useSession()
  if (!isAuthenticated) return <Navigate to="/login?next=%2Fcheckout" replace />

  return (
    <div className="page-container flex flex-col gap-5 py-5 sm:py-6">
      <title>{`${t('checkout.title')} | ${t('common.brand')}`}</title>
      <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text sm:text-3xl">
        {t('checkout.title')}
      </h1>
      <EmptyState
        className="py-14"
        icon={<ClipboardList size={22} strokeWidth={1.75} />}
        title={t('checkout.soon')}
        description={t('checkout.soonHint')}
        action={
          <Link
            to="/cart"
            className="inline-flex h-11 items-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-fg hover:bg-primary-hover focus-ring"
          >
            {t('checkout.backToCart')}
          </Link>
        }
      />
    </div>
  )
}
