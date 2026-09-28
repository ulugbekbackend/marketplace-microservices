import { EmptyState } from '@bozorcha/ui'
import { ClipboardList } from 'lucide-react'
import { useTranslation } from 'react-i18next'

/** Placeholder until the order service exposes the seller's sub-orders. */
export function OrdersPage() {
  const { t } = useTranslation()
  return (
    <div className="page-container flex flex-col gap-6 py-6 sm:py-8">
      <title>{`${t('nav.orders')} | ${t('common.panel')}`}</title>
      <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text sm:text-3xl">
        {t('nav.orders')}
      </h1>
      <EmptyState
        icon={<ClipboardList size={22} strokeWidth={1.75} />}
        title={t('orders.soon')}
        description={t('orders.soonHint')}
      />
    </div>
  )
}
