import {
  isApiError,
  useCancelOrder,
  useMockPay,
  useOrder,
  useOrderStatus,
  type Order,
  type OrderSellerGroup,
} from '@bozorcha/api-client'
import {
  Button,
  Card,
  cn,
  Dialog,
  formatMmSs,
  formatPrice,
  orderStatusTimelineTone,
  Skeleton,
  Spinner,
  Timeline,
  useCountdown,
  useToast,
  type TimelineItem,
} from '@bozorcha/ui'
import {
  ArrowLeft,
  CircleCheck,
  CircleX,
  Clock,
  ImageOff,
  MapPin,
  PackageCheck,
  RotateCcw,
  Store,
  TimerOff,
  Truck,
} from 'lucide-react'
import { useEffect, useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { OrderStatusLabel, SubOrderStatusLabel } from '../components/OrderStatusLabel'
import { QueryError } from '../components/QueryError'
import { RequireAuth } from '../components/RequireAuth'
import { formatDateTime } from '../lib/dates'
import { isNotFound } from '../lib/errors'
import { orderErrorMessage } from '../lib/orderErrors'
import { isCancellable, knownReason, MOCK_PAYMENT_ENABLED, orderNumber } from '../lib/orders'
import { NotFoundPage } from './NotFoundPage'

/** Under this many seconds the countdown turns red (design system CountdownTimer rule). */
const URGENT_SECONDS = 120

export function OrderPage() {
  return (
    <RequireAuth>
      <OrderLoader />
    </RequireAuth>
  )
}

function OrderLoader() {
  const { t } = useTranslation()
  const { orderId } = useParams()
  const order = useOrder(orderId)

  if (order.isPending) return <OrderSkeleton />
  if (order.isError) {
    if (isNotFound(order.error)) {
      return <NotFoundPage title={t('orders.notFound')} description={t('orders.notFoundHint')} />
    }
    return (
      <div className="page-container py-10">
        <QueryError
          error={order.error}
          onRetry={() => void order.refetch()}
          retrying={order.isRefetching}
        />
      </div>
    )
  }
  return <OrderView order={order.data} />
}

function OrderView({ order }: { order: Order }) {
  const { t } = useTranslation()
  const number = orderNumber(order.id)

  return (
    <div className="page-container flex flex-col gap-5 pt-5 sm:pt-6">
      <title>{`${t('orders.number', { number })} | ${t('common.brand')}`}</title>
      <Link
        to="/orders"
        className="inline-flex items-center gap-1.5 self-start rounded-sm text-sm font-semibold text-primary hover:underline focus-ring"
      >
        <ArrowLeft aria-hidden="true" size={16} strokeWidth={1.75} />
        {t('orders.backToList')}
      </Link>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex flex-col gap-1">
          <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text tabular sm:text-3xl">
            {t('orders.number', { number })}
          </h1>
          <p className="text-sm text-text-muted tabular">
            {t('orders.placedAt', { date: formatDateTime(order.created_at) })}
          </p>
        </div>
        <OrderStatusLabel status={order.status} />
      </div>

      <StatusPanel order={order} />

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-8">
        <section aria-label={t('orders.items')} className="flex min-w-0 flex-col gap-4">
          {order.sellers.map((group) => (
            <SellerGroup key={group.seller_id} group={group} />
          ))}
        </section>
        <div className="flex flex-col gap-4 lg:sticky lg:top-36">
          <Totals order={order} />
          <AddressCard order={order} />
          <History order={order} />
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ status */

function StatusPanel({ order }: { order: Order }) {
  const { t } = useTranslation()
  // Polls while PENDING, and while RESERVED past the deadline, until the server settles it.
  const status = useOrderStatus(order.id)
  const reason = knownReason(order.cancel_reason)

  switch (order.status) {
    case 'PENDING':
      return (
        <Panel
          tone="info"
          icon={<Spinner />}
          title={t('orders.pendingTitle')}
          hint={t('orders.pendingHint')}
          actions={<CancelButton order={order} />}
          live
        />
      )
    case 'RESERVED':
      return <ReservedPanel order={order} onExpire={() => void status.refetch()} />
    case 'PAID':
    case 'FULFILLING':
      return (
        <Panel
          tone="success"
          icon={<CircleCheck size={22} strokeWidth={1.75} />}
          title={t('orders.paidTitle')}
          hint={t('orders.paidHint')}
          live
        />
      )
    case 'COMPLETED':
      return (
        <Panel
          tone="primary"
          icon={<PackageCheck size={22} strokeWidth={1.75} />}
          title={t('orders.completedTitle')}
          hint={t('orders.completedHint')}
        />
      )
    case 'EXPIRED':
      return (
        <Panel
          tone="muted"
          icon={<TimerOff size={22} strokeWidth={1.75} />}
          title={t('orders.expiredTitle')}
          hint={t('orders.expiredHint')}
          actions={<CartLink />}
          live
        />
      )
    case 'CANCELLED':
      return (
        <Panel
          tone="danger"
          icon={<CircleX size={22} strokeWidth={1.75} />}
          title={t('orders.cancelledTitle')}
          hint={reason ? t(`orders.reason.${reason}`) : undefined}
          actions={reason === 'CANCELLED_BY_CUSTOMER' ? undefined : <CartLink />}
          live
        />
      )
    case 'REFUNDED':
      return (
        <Panel
          tone="info"
          icon={<RotateCcw size={22} strokeWidth={1.75} />}
          title={t('orders.refundedTitle')}
          hint={t('orders.refundedHint')}
        />
      )
  }
}

const panelTones = {
  info: 'border-info/30 bg-info-soft text-info-ink',
  success: 'border-success/30 bg-success-soft text-success-ink',
  primary: 'border-primary/30 bg-primary-soft text-primary',
  danger: 'border-danger/30 bg-danger-soft text-danger-ink',
  muted: 'border-border bg-surface-2 text-text-muted',
} as const

function Panel({
  tone,
  icon,
  title,
  hint,
  actions,
  live,
}: {
  tone: keyof typeof panelTones
  icon: ReactNode
  title: string
  hint?: string
  actions?: ReactNode
  live?: boolean
}) {
  return (
    <div
      role={live ? 'status' : undefined}
      data-testid="status-panel"
      className={cn(
        'flex flex-col gap-4 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5',
        panelTones[tone],
      )}
    >
      <div className="flex items-start gap-3">
        <span aria-hidden="true" className="mt-0.5 shrink-0">
          {icon}
        </span>
        <div className="flex flex-col gap-1">
          <p className="font-heading text-lg font-bold">{title}</p>
          {hint && <p className="text-sm text-text">{hint}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap gap-2 sm:shrink-0">{actions}</div>}
    </div>
  )
}

function CartLink() {
  const { t } = useTranslation()
  return (
    <Link
      to="/cart"
      className="inline-flex h-11 items-center rounded-lg border border-border bg-surface px-4 text-sm font-semibold text-text hover:bg-surface-2 focus-ring"
    >
      {t('orders.toCart')}
    </Link>
  )
}

/** Moment the order became RESERVED, for the progress bar; falls back to creation time. */
function reservedSince(order: Order): number {
  const entry = [...order.history].reverse().find((h) => h.to_status === 'RESERVED')
  return Date.parse(entry?.created_at ?? order.created_at)
}

function ReservedPanel({ order, onExpire }: { order: Order; onExpire: () => void }) {
  const { t } = useTranslation()
  const deadline = order.reserved_until === null ? null : Date.parse(order.reserved_until)
  const secondsLeft = useCountdown(deadline)
  const labelId = useId()

  // At zero the server expires the order lazily: ask for the status, polling takes it from there.
  const expired = deadline !== null && secondsLeft === 0
  useEffect(() => {
    if (expired) onExpire()
    // onExpire is a fresh closure every render; firing once per expiry is what matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expired])

  const totalSeconds = deadline === null ? 0 : Math.max(1, (deadline - reservedSince(order)) / 1000)
  const fraction = Math.min(1, Math.max(0, secondsLeft / totalSeconds))
  const urgent = secondsLeft <= URGENT_SECONDS

  return (
    <div
      className="flex flex-col gap-4 rounded-xl border border-border bg-surface p-4 shadow-soft sm:p-5 dark:shadow-none"
      data-testid="status-panel"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-1">
          <p id={labelId} className="flex items-center gap-1.5 text-sm font-medium text-text-muted">
            <Clock aria-hidden="true" size={16} strokeWidth={1.75} />
            {t('orders.timeLeft')}
          </p>
          <p
            role="timer"
            aria-labelledby={labelId}
            className={cn(
              'font-heading text-4xl leading-none font-extrabold tabular sm:text-5xl',
              urgent ? 'text-danger-ink' : 'text-text',
            )}
            data-testid="countdown"
          >
            {formatMmSs(secondsLeft)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <PayButton order={order} />
          <CancelButton order={order} />
        </div>
      </div>
      <div aria-hidden="true" className="h-1.5 overflow-hidden rounded-full bg-surface-2">
        <div
          className={cn(
            'h-full rounded-full transition-[width] duration-1000 ease-linear motion-reduce:transition-none',
            urgent ? 'bg-danger' : 'bg-accent',
          )}
          style={{ width: `${fraction * 100}%` }}
        />
      </div>
      <p className="text-sm text-text-muted">{t('orders.reservedHint')}</p>
    </div>
  )
}

function PayButton({ order }: { order: Order }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const pay = useMockPay()
  const [unavailable, setUnavailable] = useState(false)
  if (!MOCK_PAYMENT_ENABLED || unavailable) return null
  return (
    <Button
      variant="accent"
      loading={pay.isPending}
      title={t('orders.payHint')}
      onClick={() =>
        pay.mutate(
          { orderId: order.id },
          {
            onSuccess: () => toast({ title: t('orders.paid'), tone: 'success' }),
            onError: (error) => {
              if (isApiError(error) && error.status === 404) {
                setUnavailable(true)
                toast({ title: t('orders.mockDisabled'), tone: 'info' })
              } else {
                toast({ title: orderErrorMessage(t, error), tone: 'danger' })
              }
            },
          },
        )
      }
    >
      {t('orders.pay')}
    </Button>
  )
}

function CancelButton({ order }: { order: Order }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const cancel = useCancelOrder()
  const [open, setOpen] = useState(false)
  if (!isCancellable(order.status)) return null
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        {t('orders.cancel')}
      </Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title={t('orders.cancelTitle')}
        description={t('orders.cancelDescription')}
        closeLabel={t('common.close')}
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              {t('orders.keep')}
            </Button>
            <Button
              variant="danger"
              loading={cancel.isPending}
              onClick={() =>
                cancel.mutate(
                  { orderId: order.id },
                  {
                    onSuccess: () => {
                      setOpen(false)
                      toast({ title: t('orders.cancelled'), tone: 'success' })
                    },
                    onError: (error) => {
                      setOpen(false)
                      toast({ title: orderErrorMessage(t, error), tone: 'danger' })
                    },
                  },
                )
              }
            >
              {t('orders.cancelConfirm')}
            </Button>
          </>
        }
      />
    </>
  )
}

/* ------------------------------------------------------------------ detail */

function SellerGroup({ group }: { group: OrderSellerGroup }) {
  const { t } = useTranslation()
  const headingId = useId()
  return (
    <Card padding="none" className="overflow-hidden dark:shadow-none">
      <section aria-labelledby={headingId}>
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border bg-surface-2/60 px-4 py-3 sm:px-5">
          <h2
            id={headingId}
            className="flex min-w-0 items-center gap-2 font-heading text-base font-bold text-text"
          >
            <Store aria-hidden="true" size={18} strokeWidth={1.75} className="shrink-0" />
            <span className="truncate">{group.shop_name}</span>
          </h2>
          {group.status && <SubOrderStatusLabel status={group.status} />}
        </div>
        <ul className="divide-y divide-border">
          {group.items.map((item) => (
            <li key={item.id} className="flex gap-3 px-4 py-3 sm:px-5">
              <div className="size-14 shrink-0 overflow-hidden rounded-lg border border-border bg-surface-2">
                {item.image_url ? (
                  <img
                    src={item.image_url}
                    alt=""
                    loading="lazy"
                    className="size-full object-cover"
                  />
                ) : (
                  <span className="grid size-full place-items-center text-text-muted">
                    <ImageOff aria-hidden="true" size={18} strokeWidth={1.75} />
                  </span>
                )}
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <p className="line-clamp-2 text-sm font-medium text-text [overflow-wrap:anywhere]">
                  {item.title}
                </p>
                <p className="text-xs text-text-muted tabular">
                  {t('orders.sku', { sku: item.sku })}
                </p>
                <p className="text-sm text-text-muted tabular">
                  {t('orders.qtyPrice', { qty: item.qty, price: formatPrice(item.price_tiyin) })}
                </p>
              </div>
              <p className="shrink-0 text-sm font-semibold text-text tabular">
                {formatPrice(item.line_total_tiyin)}
              </p>
            </li>
          ))}
        </ul>
        <p className="flex justify-between gap-4 border-t border-border px-4 py-3 text-sm text-text-muted tabular sm:px-5">
          <span>{t('orders.subtotal')}</span>
          <span className="font-semibold text-text">{formatPrice(group.subtotal_tiyin)}</span>
        </p>
        <SubOrderProgress group={group} />
      </section>
    </Card>
  )
}

/** The shop's part of the order after payment: tracking, cancellation and its own history. */
function SubOrderProgress({ group }: { group: OrderSellerGroup }) {
  const { t } = useTranslation()
  if (!group.status || group.history.length === 0) return null
  const tracking =
    (group.status === 'SHIPPED' || group.status === 'DELIVERED') && group.tracking_number
  const cancelled = group.status === 'CANCELLED_BY_SELLER'
  const items: TimelineItem[] = group.history.map((entry) => ({
    id: `${entry.to_status}-${entry.created_at}`,
    title: t(`orders.subStatus.${entry.to_status}`),
    time: formatDateTime(entry.created_at),
    dateTime: entry.created_at,
    tone: orderStatusTimelineTone(entry.to_status),
  }))
  return (
    <div className="flex flex-col gap-3 border-t border-border px-4 py-4 sm:px-5">
      {tracking && (
        <div
          className="flex items-start gap-3 rounded-lg bg-purple-soft px-3 py-2.5"
          data-testid="tracking"
        >
          <Truck
            aria-hidden="true"
            size={20}
            strokeWidth={1.75}
            className="mt-0.5 shrink-0 text-purple-ink"
          />
          <div className="flex min-w-0 flex-col">
            <span className="text-xs text-text-muted">{t('orders.tracking')}</span>
            <span className="font-semibold [overflow-wrap:anywhere] text-text tabular">
              {group.tracking_number}
            </span>
            <span className="text-xs text-text-muted">{t('orders.trackingHint')}</span>
          </div>
        </div>
      )}
      {cancelled && (
        <div
          role="note"
          className="flex items-start gap-3 rounded-lg bg-danger-soft px-3 py-2.5"
          data-testid="seller-cancelled"
        >
          <CircleX
            aria-hidden="true"
            size={20}
            strokeWidth={1.75}
            className="mt-0.5 shrink-0 text-danger-ink"
          />
          <div className="flex min-w-0 flex-col gap-0.5 text-sm">
            <span className="font-semibold text-text">{t('orders.cancelledBySeller')}</span>
            {group.cancel_reason && (
              <span className="[overflow-wrap:anywhere] text-text">
                {t('orders.sellerReason', { reason: group.cancel_reason })}
              </span>
            )}
            <span className="text-text-muted">{t('orders.refundNote')}</span>
          </div>
        </div>
      )}
      <Timeline compact label={t('orders.shopHistory', { shop: group.shop_name })} items={items} />
    </div>
  )
}

function Totals({ order }: { order: Order }) {
  const { t } = useTranslation()
  // Lines, not units: the same number the order list shows (`items_count`).
  const count = order.sellers.reduce((sum, group) => sum + group.items.length, 0)
  return (
    <Card className="flex flex-col gap-2 dark:shadow-none">
      <p className="flex justify-between gap-4 text-sm text-text-muted tabular">
        <span>{t('orders.itemsCount', { count })}</span>
      </p>
      <p className="flex items-baseline justify-between gap-4 tabular">
        <span className="font-semibold text-text">{t('orders.total')}</span>
        <span
          className="font-heading text-2xl font-extrabold text-accent-ink"
          data-testid="order-total"
        >
          {formatPrice(order.total_tiyin)}
        </span>
      </p>
    </Card>
  )
}

function AddressCard({ order }: { order: Order }) {
  const { t } = useTranslation()
  const a = order.delivery_address
  return (
    <Card className="flex flex-col gap-2 dark:shadow-none">
      <h2 className="flex items-center gap-2 font-heading text-base font-bold text-text">
        <MapPin aria-hidden="true" size={18} strokeWidth={1.75} />
        {t('orders.address')}
      </h2>
      <address className="flex flex-col gap-0.5 text-sm text-text not-italic [overflow-wrap:anywhere]">
        <span className="font-medium">{a.full_name}</span>
        <span className="tabular">{a.phone}</span>
        <span>
          {a.region}, {a.city}
        </span>
        <span>{a.street}</span>
        {a.notes && <span className="text-text-muted">{a.notes}</span>}
      </address>
    </Card>
  )
}

function History({ order }: { order: Order }) {
  const { t } = useTranslation()
  if (order.history.length === 0) return null
  return (
    <Card className="flex flex-col gap-3 dark:shadow-none">
      <h2 className="font-heading text-base font-bold text-text">{t('orders.history')}</h2>
      <Timeline
        compact
        label={t('orders.history')}
        items={order.history.map((entry) => {
          const reason = knownReason(entry.reason)
          return {
            id: `${entry.to_status}-${entry.created_at}`,
            title: t(`orders.status.${entry.to_status}`),
            time: formatDateTime(entry.created_at),
            dateTime: entry.created_at,
            tone: orderStatusTimelineTone(entry.to_status),
            description:
              reason && entry.to_status !== 'EXPIRED' ? t(`orders.reason.${reason}`) : undefined,
          }
        })}
      />
    </Card>
  )
}

function OrderSkeleton() {
  const { t } = useTranslation()
  return (
    <div
      className="page-container flex flex-col gap-5 pt-5 sm:pt-6"
      role="status"
      aria-busy="true"
      aria-label={t('common.loading')}
    >
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-9 w-64 max-w-full" />
      <Skeleton className="h-32 rounded-xl" />
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-8">
        <Skeleton className="h-64 rounded-xl" />
        <div className="flex flex-col gap-4">
          <Skeleton className="h-24 rounded-xl" />
          <Skeleton className="h-36 rounded-xl" />
        </div>
      </div>
    </div>
  )
}
