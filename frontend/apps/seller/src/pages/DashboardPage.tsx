import { useSellerApplication, useSellerProducts, type ProductStatus } from '@bozorcha/api-client'
import { Card, EmptyState, Skeleton } from '@bozorcha/ui'
import { ChartNoAxesColumn } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

/** Product counts per status, each linking to the filtered list. */
function StatusCount({ status }: { status?: ProductStatus }) {
  const { t } = useTranslation()
  const query = useSellerProducts({ status, page: 1, page_size: 1 })
  const label = status ? t(`productStatus.${status}`) : t('dashboard.allProducts')
  return (
    <Link
      to={status ? `/products?status=${status}` : '/products'}
      className="group rounded-xl focus-ring"
    >
      <Card className="flex h-full flex-col gap-1 transition-colors duration-150 ease-out group-hover:border-primary">
        <span className="text-sm text-text-muted">{label}</span>
        {query.isPending ? (
          <Skeleton className="h-9 w-16" />
        ) : query.isError ? (
          <span className="font-heading text-3xl font-extrabold text-text-muted">—</span>
        ) : (
          <span className="font-heading text-3xl font-extrabold text-text tabular">
            {query.data.total}
          </span>
        )}
      </Card>
    </Link>
  )
}

export function DashboardPage() {
  const { t } = useTranslation()
  const application = useSellerApplication()
  const shopName = application.data?.shop_name
  return (
    <div className="page-container flex flex-col gap-6 py-6 sm:py-8">
      <title>{`${t('nav.dashboard')} | ${t('common.panel')}`}</title>
      <div>
        <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text sm:text-3xl">
          {shopName ? t('dashboard.greetingShop', { name: shopName }) : t('dashboard.greeting')}
        </h1>
        <p className="mt-1 text-sm text-text-muted">{t('dashboard.subtitle')}</p>
      </div>
      <section aria-labelledby="dashboard-products">
        <h2 id="dashboard-products" className="mb-3 font-heading text-lg font-bold text-text">
          {t('dashboard.products')}
        </h2>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatusCount />
          <StatusCount status="active" />
          <StatusCount status="draft" />
          <StatusCount status="archived" />
        </div>
      </section>
      <EmptyState
        icon={<ChartNoAxesColumn size={22} strokeWidth={1.75} />}
        title={t('dashboard.statsSoon')}
        description={t('dashboard.statsSoonHint')}
      />
    </div>
  )
}
