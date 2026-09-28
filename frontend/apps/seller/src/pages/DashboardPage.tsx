import {
  useSellerApplication,
  useSellerOrders,
  useSellerOrderStats,
  useSellerProducts,
  type ProductStatus,
  type SellerPeriodStats,
  type SellerStats,
} from '@bozorcha/api-client'
import { Card, EmptyState, formatPrice, Skeleton } from '@bozorcha/ui'
import { BellRing, ChartNoAxesColumn, ClipboardList, Inbox } from 'lucide-react'
import { lazy, Suspense, useId, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { QueryError } from '../components/QueryError'
import { SubOrderStatusBadge } from '../components/SubOrderStatusBadge'
import { formatDateTime } from '../lib/dates'
import { orderNumber } from '../lib/orders'
import { dayLabelLong, hasNoOrders, summarize, toChartPoints, type ChartPoint } from '../lib/stats'

// Recharts is large: it loads with the chart, not with the panel shell.
const RevenueChart = lazy(async () => ({
  default: (await import('../components/RevenueChart')).RevenueChart,
}))

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
      <Card
        padding="sm"
        className="flex h-full flex-col gap-0.5 transition-colors duration-150 ease-out group-hover:border-primary dark:shadow-none"
      >
        <span className="text-sm text-text-muted">{label}</span>
        {query.isPending ? (
          <Skeleton className="h-8 w-12" />
        ) : query.isError ? (
          <span className="font-heading text-2xl font-extrabold text-text-muted">—</span>
        ) : (
          <span className="font-heading text-2xl font-extrabold text-text tabular">
            {query.data.total}
          </span>
        )}
      </Card>
    </Link>
  )
}

/* ------------------------------------------------------------ new orders */

function NewOrdersCallout({ count }: { count: number }) {
  const { t } = useTranslation()
  if (count === 0) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-border bg-surface px-4 py-3">
        <span
          aria-hidden="true"
          className="grid size-10 shrink-0 place-items-center rounded-full bg-surface-2 text-text-muted"
        >
          <Inbox size={20} strokeWidth={1.75} />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-text">{t('dashboard.noNewOrders')}</p>
          <p className="text-sm text-text-muted">{t('dashboard.noNewOrdersHint')}</p>
        </div>
      </div>
    )
  }
  return (
    <section
      aria-label={t('dashboard.newOrders', { count })}
      className="flex flex-col gap-4 rounded-xl border border-accent/50 bg-accent-soft p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5"
      data-testid="new-orders"
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="grid size-11 shrink-0 place-items-center rounded-full bg-accent text-accent-fg"
        >
          <BellRing size={20} strokeWidth={1.75} />
        </span>
        <div className="min-w-0">
          <p className="font-heading text-xl font-extrabold text-text tabular">
            {t('dashboard.newOrders', { count })}
          </p>
          <p className="text-sm text-text">{t('dashboard.newOrdersHint')}</p>
        </div>
      </div>
      <Link
        to="/orders?status=NEW"
        className="inline-flex h-11 shrink-0 items-center justify-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-fg transition-colors duration-150 ease-out hover:bg-primary-hover focus-ring"
      >
        {t('dashboard.openNew')}
      </Link>
    </section>
  )
}

/* --------------------------------------------------------------- periods */

function PeriodCard({ label, stats }: { label: string; stats: SellerPeriodStats }) {
  const { t } = useTranslation()
  return (
    <Card className="flex flex-col gap-3 dark:shadow-none" data-testid="period-card">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-text-muted">{label}</h3>
        <span className="text-xs text-text-muted tabular">
          {t('dashboard.ordersCount', { count: stats.orders })}
        </span>
      </div>
      <div className="flex flex-col">
        <span className="text-xs text-text-muted">{t('dashboard.gross')}</span>
        <span className="font-heading text-2xl leading-tight font-extrabold text-text tabular">
          {formatPrice(stats.gross_tiyin)}
        </span>
      </div>
      <p className="flex flex-wrap items-baseline justify-between gap-x-3 border-t border-border pt-2 text-sm tabular">
        <span className="text-text-muted">{t('dashboard.net')}</span>
        <span className="font-semibold text-success-ink">{formatPrice(stats.net_tiyin)}</span>
      </p>
    </Card>
  )
}

function PeriodSkeleton() {
  return (
    <Card className="flex flex-col gap-3 dark:shadow-none" aria-hidden="true">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-8 w-40" />
      <Skeleton className="h-4 w-full" />
    </Card>
  )
}

/* ----------------------------------------------------------------- chart */

function Legend() {
  const { t } = useTranslation()
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-text-muted">
      <li className="flex items-center gap-2">
        <span aria-hidden="true" className="h-0.5 w-4 rounded-full bg-chart-gross" />
        {t('dashboard.gross')}
      </li>
      <li className="flex items-center gap-2">
        <span aria-hidden="true" className="h-0.5 w-4 rounded-full bg-chart-net" />
        {t('dashboard.net')}
      </li>
    </ul>
  )
}

/** The chart's numbers for assistive technology. */
function ChartTable({ points }: { points: ChartPoint[] }) {
  const { t } = useTranslation()
  return (
    // A table never shrinks below its content: the wrapper carries sr-only.
    <div className="sr-only">
      <table>
        <caption>{t('dashboard.chartTable')}</caption>
        <thead>
          <tr>
            <th scope="col">{t('dashboard.date')}</th>
            <th scope="col">{t('dashboard.orders')}</th>
            <th scope="col">{t('dashboard.gross')}</th>
            <th scope="col">{t('dashboard.net')}</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.date}>
              <th scope="row">{dayLabelLong(point.date)}</th>
              <td>{point.orders}</td>
              <td>{formatPrice(point.gross)}</td>
              <td>{formatPrice(point.net)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SalesChart({ stats }: { stats: SellerStats }) {
  const { t } = useTranslation()
  const headingId = useId()
  const points = useMemo(() => toChartPoints(stats.daily), [stats.daily])
  const summary = summarize(points)
  const empty = hasNoOrders(stats)

  return (
    <Card className="flex min-w-0 flex-col gap-4 dark:shadow-none">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <h2 id={headingId} className="font-heading text-lg font-bold text-text">
          {t('dashboard.chartTitle')}
        </h2>
        {!empty && <Legend />}
      </div>
      {empty ? (
        <EmptyState
          icon={<ChartNoAxesColumn size={22} strokeWidth={1.75} />}
          title={t('dashboard.noSales')}
          description={t('dashboard.noSalesHint')}
          action={
            <Link
              to="/products"
              className="inline-flex h-11 items-center rounded-lg border border-border bg-surface px-4 text-sm font-semibold text-text hover:bg-surface-2 focus-ring"
            >
              {t('dashboard.toProducts')}
            </Link>
          }
        />
      ) : (
        <figure aria-labelledby={headingId} className="flex flex-col gap-3">
          <Suspense
            fallback={
              <Skeleton
                className="h-56 w-full rounded-lg sm:h-64"
                aria-label={t('dashboard.chartLoading')}
              />
            }
          >
            <RevenueChart points={points} />
          </Suspense>
          <figcaption className="text-sm text-text-muted" data-testid="chart-summary">
            {summary.best
              ? t('dashboard.chartSummary', {
                  orders: summary.orders,
                  gross: formatPrice(summary.gross),
                  net: formatPrice(summary.net),
                  best: dayLabelLong(summary.best.date),
                })
              : t('dashboard.chartSummaryEmpty')}
          </figcaption>
          <ChartTable points={points} />
        </figure>
      )}
    </Card>
  )
}

/* ---------------------------------------------------------------- recent */

function RecentOrders() {
  const { t } = useTranslation()
  const orders = useSellerOrders({ page: 1, page_size: 5 })
  const headingId = useId()

  let body
  if (orders.isPending) {
    body = (
      <ul className="flex flex-col divide-y divide-border" aria-hidden="true">
        {Array.from({ length: 3 }, (_, i) => (
          <li key={i} className="flex items-center justify-between gap-3 py-3">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-6 w-20 rounded-full" />
          </li>
        ))}
      </ul>
    )
  } else if (orders.isError) {
    body = (
      <QueryError
        error={orders.error}
        onRetry={() => void orders.refetch()}
        retrying={orders.isFetching}
      />
    )
  } else if (orders.data.items.length === 0) {
    body = (
      <EmptyState
        icon={<ClipboardList size={22} strokeWidth={1.75} />}
        title={t('dashboard.noOrders')}
        description={t('dashboard.noOrdersHint')}
      />
    )
  } else {
    body = (
      <ul className="-mx-2 flex flex-col">
        {orders.data.items.map((order) => (
          <li key={order.id}>
            <Link
              to={`/orders/${order.id}`}
              className="flex items-center justify-between gap-3 rounded-lg px-2 py-2.5 transition-colors duration-150 ease-out hover:bg-surface-2 focus-ring"
            >
              <span className="flex min-w-0 flex-col">
                <span className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-sm font-semibold text-text tabular">
                    {t('orders.numberValue', { number: orderNumber(order.order_id) })}
                  </span>
                  <span className="text-xs text-text-muted tabular">
                    {formatDateTime(order.created_at)}
                  </span>
                </span>
                <span className="truncate text-sm text-text-muted">{order.customer_name}</span>
              </span>
              <span className="flex shrink-0 flex-col items-end gap-1">
                <span className="text-sm font-semibold text-text tabular">
                  {formatPrice(order.subtotal_tiyin)}
                </span>
                <SubOrderStatusBadge status={order.status} />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    )
  }

  return (
    <Card className="flex min-w-0 flex-col gap-3 dark:shadow-none">
      <section aria-labelledby={headingId} className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <h2 id={headingId} className="font-heading text-lg font-bold text-text">
            {t('dashboard.recent')}
          </h2>
          <Link
            to="/orders"
            className="rounded-sm text-sm font-semibold text-primary hover:underline focus-ring"
          >
            {t('dashboard.allOrders')}
          </Link>
        </div>
        {body}
      </section>
    </Card>
  )
}

/* ------------------------------------------------------------------ page */

function Sales() {
  const { t } = useTranslation()
  const stats = useSellerOrderStats()

  if (stats.isError) {
    return (
      <QueryError
        error={stats.error}
        onRetry={() => void stats.refetch()}
        retrying={stats.isFetching}
      />
    )
  }
  const data = stats.data
  return (
    <div className="flex flex-col gap-4">
      {data ? (
        <NewOrdersCallout count={data.by_status.NEW} />
      ) : (
        <Skeleton className="h-20 rounded-xl" />
      )}
      <section aria-labelledby="dashboard-sales" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 id="dashboard-sales" className="font-heading text-lg font-bold text-text">
            {t('dashboard.sales')}
          </h2>
          <p className="text-xs text-text-muted">{t('dashboard.salesNote')}</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {data ? (
            <>
              <PeriodCard label={t('dashboard.today')} stats={data.today} />
              <PeriodCard label={t('dashboard.week')} stats={data.week} />
              <PeriodCard label={t('dashboard.month')} stats={data.month} />
            </>
          ) : (
            <>
              <PeriodSkeleton />
              <PeriodSkeleton />
              <PeriodSkeleton />
            </>
          )}
        </div>
      </section>
      {data ? (
        <SalesChart stats={data} />
      ) : (
        <Card className="flex flex-col gap-4 dark:shadow-none" aria-hidden="true">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-56 w-full rounded-lg sm:h-64" />
        </Card>
      )}
    </div>
  )
}

export function DashboardPage() {
  const { t } = useTranslation()
  const application = useSellerApplication()
  const shopName = application.data?.shop_name
  const stats = useSellerOrderStats()
  return (
    <div
      className="page-container flex flex-col gap-6 py-6 sm:py-8"
      aria-busy={stats.isPending || undefined}
    >
      <title>{`${t('nav.dashboard')} | ${t('common.panel')}`}</title>
      <div>
        <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text sm:text-3xl">
          {shopName ? t('dashboard.greetingShop', { name: shopName }) : t('dashboard.greeting')}
        </h1>
        <p className="mt-1 text-sm text-text-muted">{t('dashboard.subtitle')}</p>
      </div>
      <Sales />
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <RecentOrders />
        <section aria-labelledby="dashboard-products" className="flex flex-col gap-3">
          <h2 id="dashboard-products" className="font-heading text-lg font-bold text-text">
            {t('dashboard.products')}
          </h2>
          <div className="grid grid-cols-2 gap-3">
            <StatusCount />
            <StatusCount status="active" />
            <StatusCount status="draft" />
            <StatusCount status="archived" />
          </div>
        </section>
      </div>
    </div>
  )
}
