import { queryKeys, useOrder, useOrderStatus, type Order } from '@bozorcha/api-client'
import { Skeleton, Spinner } from '@bozorcha/ui'
import { CircleCheck, CircleX, Hourglass, RotateCcw, TimerOff } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useSearchParams } from 'react-router'
import { QueryError } from '../components/QueryError'
import { RequireAuth } from '../components/RequireAuth'
import { StatusPanel } from '../components/StatusPanel'
import { isNotFound } from '../lib/errors'
import {
  awaitsLateReservation,
  isPaid,
  knownReason,
  orderNumber,
  PAYMENT_METHODS,
} from '../lib/orders'
import { NotFoundPage } from './NotFoundPage'

/** After this long without a confirmation the page suggests going back to pay another way. */
export const SLOW_PAYMENT_MS = 60_000

/** Where Payme / Click send the customer back, and where the test payment lands. */
export function PaymentResultPage() {
  return (
    <RequireAuth>
      <PaymentResult />
    </RequireAuth>
  )
}

function PaymentResult() {
  const { t } = useTranslation()
  const { orderId } = useParams()
  const order = useOrder(orderId)

  if (order.isPending) return <ResultSkeleton />
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
  return <ResultView order={order.data} />
}

function ResultView({ order }: { order: Order }) {
  const { t } = useTranslation()
  const [params] = useSearchParams()
  const method = PAYMENT_METHODS.find((m) => m === params.get('provider'))
  const number = orderNumber(order.id)
  const waiting = order.status === 'PENDING' || order.status === 'RESERVED'
  // Polls until payment.paid reaches the order service; the detail follows the status.
  useOrderStatus(order.id, { poll: waiting || awaitsLateReservation(order) })
  const slow = useElapsed(waiting, SLOW_PAYMENT_MS)
  // The order service empties the cart when the payment lands: the header's count is stale.
  const queryClient = useQueryClient()
  const paid = isPaid(order.status)
  useEffect(() => {
    if (paid) void queryClient.invalidateQueries({ queryKey: queryKeys.cart })
  }, [paid, queryClient])

  return (
    <div className="page-container flex max-w-2xl flex-col gap-5 pt-6 sm:pt-10">
      <title>{`${t('payment.resultTitle', { number })} | ${t('common.brand')}`}</title>
      <div className="flex flex-col gap-1">
        <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text tabular sm:text-3xl">
          {t('payment.resultTitle', { number })}
        </h1>
        {method && (
          <p className="text-sm text-text-muted">
            {t('payment.via', { provider: t(`payment.provider.${method}`) })}
          </p>
        )}
      </div>
      <Outcome order={order} slow={slow} />
    </div>
  )
}

function Outcome({ order, slow }: { order: Order; slow: boolean }) {
  const { t } = useTranslation()
  const toOrder = <OrderLink orderId={order.id} label={t('payment.backToOrder')} />

  if (awaitsLateReservation(order)) {
    return (
      <StatusPanel
        tone="info"
        icon={<Spinner />}
        title={t('orders.latePaymentTitle')}
        hint={t('orders.latePaymentHint')}
        actions={toOrder}
        live
      />
    )
  }
  if (isPaid(order.status)) {
    return (
      <StatusPanel
        tone="success"
        icon={<CircleCheck size={22} strokeWidth={1.75} />}
        title={t('payment.paidTitle')}
        hint={t('payment.paidHint')}
        actions={<OrderLink orderId={order.id} label={t('payment.viewOrder')} primary />}
        live
      />
    )
  }
  switch (order.status) {
    case 'EXPIRED':
      return (
        <StatusPanel
          tone="muted"
          icon={<TimerOff size={22} strokeWidth={1.75} />}
          title={t('orders.expiredTitle')}
          hint={t('orders.expiredHint')}
          actions={toOrder}
          live
        />
      )
    case 'CANCELLED': {
      const reason = knownReason(order.cancel_reason)
      return (
        <StatusPanel
          tone="danger"
          icon={<CircleX size={22} strokeWidth={1.75} />}
          title={t('orders.cancelledTitle')}
          hint={reason ? t(`orders.reason.${reason}`) : undefined}
          actions={toOrder}
          live
        />
      )
    }
    case 'REFUNDED':
      return (
        <StatusPanel
          tone="info"
          icon={<RotateCcw size={22} strokeWidth={1.75} />}
          title={t('orders.refundedTitle')}
          hint={t('orders.refundedHint')}
          actions={toOrder}
          live
        />
      )
  }
  return slow ? (
    <StatusPanel
      tone="muted"
      icon={<Hourglass size={22} strokeWidth={1.75} />}
      title={t('payment.slowTitle')}
      hint={t('payment.slowHint')}
      actions={toOrder}
      live
    />
  ) : (
    <StatusPanel
      tone="info"
      icon={<Spinner />}
      title={t('payment.waitingTitle')}
      hint={t('payment.waitingHint')}
      actions={toOrder}
      live
    />
  )
}

function OrderLink({
  orderId,
  label,
  primary,
}: {
  orderId: string
  label: string
  primary?: boolean
}) {
  return (
    <Link
      to={`/orders/${orderId}`}
      className={
        primary
          ? 'inline-flex h-11 items-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-fg hover:bg-primary-hover focus-ring'
          : 'inline-flex h-11 items-center rounded-lg border border-border bg-surface px-4 text-sm font-semibold text-text hover:bg-surface-2 focus-ring'
      }
    >
      {label}
    </Link>
  )
}

/** True once `active` has stayed true for `ms`; resets when it turns false. */
function useElapsed(active: boolean, ms: number): boolean {
  const [elapsed, setElapsed] = useState(false)
  useEffect(() => {
    if (!active) return
    const timer = window.setTimeout(() => setElapsed(true), ms)
    return () => {
      window.clearTimeout(timer)
      setElapsed(false)
    }
  }, [active, ms])
  return active && elapsed
}

function ResultSkeleton() {
  const { t } = useTranslation()
  return (
    <div
      className="page-container flex max-w-2xl flex-col gap-5 pt-6 sm:pt-10"
      role="status"
      aria-busy="true"
      aria-label={t('common.loading')}
    >
      <Skeleton className="h-9 w-72 max-w-full" />
      <Skeleton className="h-28 rounded-xl" />
    </div>
  )
}
