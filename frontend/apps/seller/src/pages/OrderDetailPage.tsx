import {
  isApiError,
  useSellerOrder,
  type SellerSubOrderDetail,
  type SubOrderHistoryEntry,
} from '@bozorcha/api-client'
import {
  Card,
  cn,
  EmptyState,
  formatE164,
  formatPrice,
  orderStatusTimelineTone,
  Skeleton,
  Timeline,
  type TimelineItem,
} from '@bozorcha/ui'
import { ArrowLeft, ImageOff, MapPin, Phone, SearchX, Truck } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { QueryError } from '../components/QueryError'
import { StatusActions } from '../components/StatusActions'
import { SubOrderStatusBadge } from '../components/SubOrderStatusBadge'
import { formatDateTime } from '../lib/dates'
import { formatRate, isOrderActive, orderNumber, upcomingSteps } from '../lib/orders'

export function OrderDetailPage() {
  const { t } = useTranslation()
  const { subOrderId } = useParams()
  const order = useSellerOrder(subOrderId)

  if (order.isPending) return <DetailSkeleton />
  if (order.isError) {
    const notFound = isApiError(order.error) && order.error.status === 404
    return (
      <div className="page-container flex flex-col gap-5 py-6 sm:py-8">
        <BackLink />
        {notFound ? (
          <EmptyState
            icon={<SearchX size={22} strokeWidth={1.75} />}
            title={t('order.notFound')}
            description={t('order.notFoundHint')}
          />
        ) : (
          <QueryError
            error={order.error}
            onRetry={() => void order.refetch()}
            retrying={order.isFetching}
          />
        )}
      </div>
    )
  }
  return <OrderView order={order.data} />
}

function BackLink() {
  const { t } = useTranslation()
  return (
    <Link
      to="/orders"
      className="inline-flex items-center gap-1.5 self-start rounded-sm text-sm font-semibold text-primary hover:underline focus-ring"
    >
      <ArrowLeft aria-hidden="true" size={16} strokeWidth={1.75} />
      {t('order.back')}
    </Link>
  )
}

function OrderView({ order }: { order: SellerSubOrderDetail }) {
  const { t } = useTranslation()
  const number = orderNumber(order.order_id)
  const active = isOrderActive(order.order_status)
  const terminal = order.status === 'DELIVERED' || order.status === 'CANCELLED_BY_SELLER'

  return (
    <div className="page-container flex flex-col gap-5 py-6 sm:py-8">
      <title>{`${t('order.title', { number })} | ${t('common.panel')}`}</title>
      <BackLink />
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text tabular sm:text-3xl">
            {t('order.title', { number })}
          </h1>
          <p className="text-sm text-text-muted tabular">
            {t('order.placedAt', { date: formatDateTime(order.created_at) })}
          </p>
        </div>
        <SubOrderStatusBadge status={order.status} className="mt-1" />
      </div>

      <NextStep order={order} active={active} terminal={terminal} />

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-6">
        <div className="flex min-w-0 flex-col gap-5">
          <Items order={order} />
        </div>
        <div className="flex min-w-0 flex-col gap-5">
          <Customer order={order} />
          <History order={order} />
        </div>
      </div>
    </div>
  )
}

/** What the seller should do now, with the buttons for it. */
function NextStep({
  order,
  active,
  terminal,
}: {
  order: SellerSubOrderDetail
  active: boolean
  terminal: boolean
}) {
  const { t } = useTranslation()
  if (!active && !terminal) {
    return (
      <p
        role="status"
        className="rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-text"
      >
        {t('order.inactive', { status: t(`orderStatus.${order.order_status}`) })}
      </p>
    )
  }
  const cancelled = order.status === 'CANCELLED_BY_SELLER'
  return (
    <div
      className={cn(
        'flex flex-col gap-4 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5',
        cancelled
          ? 'border-danger/30 bg-danger-soft'
          : terminal
            ? 'border-primary/30 bg-primary-soft'
            : 'border-border bg-surface shadow-soft dark:shadow-none',
      )}
      data-testid="next-step"
    >
      <div className="flex min-w-0 flex-col gap-1">
        <p className="text-sm text-text">{t(`order.hint.${order.status}`)}</p>
        {order.status === 'SHIPPED' && order.tracking_number && (
          <p className="flex items-center gap-1.5 text-sm font-semibold text-text tabular">
            <Truck aria-hidden="true" size={16} strokeWidth={1.75} />
            {t('order.tracking', { number: order.tracking_number })}
          </p>
        )}
      </div>
      <StatusActions order={order} />
    </div>
  )
}

function Items({ order }: { order: SellerSubOrderDetail }) {
  const { t } = useTranslation()
  const headingId = useId()
  const rate = formatRate(order.commission_rate)
  return (
    <Card padding="none" className="overflow-hidden dark:shadow-none">
      <section aria-labelledby={headingId}>
        <h2
          id={headingId}
          className="border-b border-border bg-surface-2/60 px-4 py-3 font-heading text-base font-bold text-text sm:px-5"
        >
          {t('order.items')}
        </h2>
        <ul className="divide-y divide-border">
          {order.items.map((item) => (
            <li key={item.id} className="flex gap-3 px-4 py-3 sm:px-5">
              <div className="size-16 shrink-0 overflow-hidden rounded-lg border border-border bg-surface-2">
                {item.image ? (
                  <img src={item.image} alt="" loading="lazy" className="size-full object-cover" />
                ) : (
                  <span className="grid size-full place-items-center text-text-muted">
                    <ImageOff aria-hidden="true" size={18} strokeWidth={1.75} />
                  </span>
                )}
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <p className="line-clamp-2 text-sm font-medium [overflow-wrap:anywhere] text-text">
                  {item.title}
                </p>
                <p className="text-xs [overflow-wrap:anywhere] text-text-muted tabular">
                  {t('order.sku', { sku: item.sku })}
                </p>
                <p className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm text-text-muted tabular">
                  <span className="whitespace-nowrap">
                    {t('order.qtyPrice', { qty: item.qty, price: formatPrice(item.price_tiyin) })}
                  </span>
                  <span className="font-semibold whitespace-nowrap text-text sm:hidden">
                    {formatPrice(item.line_total_tiyin)}
                  </span>
                </p>
              </div>
              <p className="hidden shrink-0 text-sm font-semibold text-text tabular sm:block">
                {formatPrice(item.line_total_tiyin)}
              </p>
            </li>
          ))}
        </ul>
        <dl className="flex flex-col gap-2 border-t border-border px-4 py-4 text-sm tabular sm:px-5">
          <div className="flex justify-between gap-4">
            <dt className="text-text-muted">{t('order.subtotal')}</dt>
            <dd className="text-text">{formatPrice(order.subtotal_tiyin)}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-text-muted">{t('order.commission', { rate })}</dt>
            <dd className="text-text">−{formatPrice(order.commission_tiyin)}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-4 border-t border-border pt-2">
            <dt className="font-semibold text-text">{t('order.net')}</dt>
            <dd
              className={cn(
                'font-heading text-xl font-extrabold',
                order.status === 'CANCELLED_BY_SELLER'
                  ? 'text-text-muted line-through'
                  : 'text-success-ink',
              )}
              data-testid="order-net"
            >
              {formatPrice(order.net_tiyin)}
            </dd>
          </div>
        </dl>
      </section>
    </Card>
  )
}

function Customer({ order }: { order: SellerSubOrderDetail }) {
  const { t } = useTranslation()
  const a = order.delivery_address
  const phone = formatE164(a.phone)
  return (
    <Card className="flex flex-col gap-3 dark:shadow-none">
      <h2 className="flex items-center gap-2 font-heading text-base font-bold text-text">
        <MapPin aria-hidden="true" size={18} strokeWidth={1.75} />
        {t('order.customer')}
      </h2>
      <address className="flex flex-col gap-0.5 text-sm [overflow-wrap:anywhere] text-text not-italic">
        <span className="font-semibold">{a.full_name}</span>
        <span>
          {a.region}, {a.city}
        </span>
        <span>{a.street}</span>
        {a.notes && <span className="text-text-muted">{a.notes}</span>}
      </address>
      <a
        href={`tel:${a.phone}`}
        aria-label={t('order.call', { phone })}
        className="inline-flex h-11 items-center gap-2 self-start rounded-lg border border-border bg-surface px-4 text-sm font-semibold text-text tabular transition-colors duration-150 ease-out hover:bg-surface-2 focus-ring"
      >
        <Phone aria-hidden="true" size={18} strokeWidth={1.75} />
        {phone}
      </a>
    </Card>
  )
}

function historyItem(
  entry: SubOrderHistoryEntry,
  order: SellerSubOrderDetail,
  t: ReturnType<typeof useTranslation>['t'],
): TimelineItem {
  let description: string | undefined
  if (entry.to_status === 'SHIPPED' && order.tracking_number) {
    description = t('order.tracking', { number: order.tracking_number })
  } else if (entry.reason) {
    description = entry.reason
  }
  return {
    id: `${entry.to_status}-${entry.created_at}`,
    title: t(`subOrderStatus.${entry.to_status}`),
    time: formatDateTime(entry.created_at),
    dateTime: entry.created_at,
    description,
    tone: orderStatusTimelineTone(entry.to_status),
  }
}

function History({ order }: { order: SellerSubOrderDetail }) {
  const { t } = useTranslation()
  const items = order.history.map((entry) => historyItem(entry, order, t))
  const upcoming = isOrderActive(order.order_status)
    ? upcomingSteps(order.status).map((step) => ({ id: step, title: t(`subOrderStep.${step}`) }))
    : []
  return (
    <Card className="flex flex-col gap-3 dark:shadow-none">
      <h2 className="font-heading text-base font-bold text-text">{t('order.history')}</h2>
      <Timeline label={t('order.history')} items={items} upcoming={upcoming} />
    </Card>
  )
}

function DetailSkeleton() {
  const { t } = useTranslation()
  return (
    <div
      className="page-container flex flex-col gap-5 py-6 sm:py-8"
      role="status"
      aria-busy="true"
      aria-label={t('common.loading')}
    >
      <Skeleton className="h-4 w-40" />
      <Skeleton className="h-9 w-64 max-w-full" />
      <Skeleton className="h-20 rounded-xl" />
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-6">
        <Skeleton className="h-72 rounded-xl" />
        <div className="flex flex-col gap-5">
          <Skeleton className="h-40 rounded-xl" />
          <Skeleton className="h-48 rounded-xl" />
        </div>
      </div>
    </div>
  )
}
