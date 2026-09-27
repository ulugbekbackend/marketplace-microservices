import { useOrders, type OrderSummary } from '@bozorcha/api-client'
import { EmptyState, formatPrice, Pagination, Skeleton } from '@bozorcha/ui'
import { ChevronRight, ClipboardList } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import { OrderStatusLabel } from '../components/OrderStatusLabel'
import { QueryError } from '../components/QueryError'
import { RequireAuth } from '../components/RequireAuth'
import { RouterLink } from '../components/RouterLink'
import { formatDateTime } from '../lib/dates'
import { orderNumber } from '../lib/orders'

const ORDERS_PAGE_SIZE = 10

export function OrdersPage() {
  return (
    <RequireAuth>
      <Orders />
    </RequireAuth>
  )
}

function Orders() {
  const { t } = useTranslation()
  const [searchParams] = useSearchParams()
  const page = Math.max(1, Number.parseInt(searchParams.get('page') ?? '1', 10) || 1)
  const orders = useOrders({ page, page_size: ORDERS_PAGE_SIZE })
  const pageCount = orders.data ? Math.ceil(orders.data.total / ORDERS_PAGE_SIZE) : 0

  return (
    <div className="page-container flex flex-col gap-5 pt-5 sm:pt-6">
      <title>{`${t('orders.title')} | ${t('common.brand')}`}</title>
      <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text sm:text-3xl">
        {t('orders.title')}
      </h1>
      {orders.isPending ? (
        <OrdersSkeleton />
      ) : orders.isError ? (
        <QueryError
          error={orders.error}
          onRetry={() => void orders.refetch()}
          retrying={orders.isRefetching}
        />
      ) : orders.data.items.length === 0 ? (
        <EmptyState
          className="py-14"
          icon={<ClipboardList size={22} strokeWidth={1.75} />}
          title={t('orders.empty')}
          description={t('orders.emptyHint')}
          action={
            <Link
              to="/catalog"
              className="inline-flex h-11 items-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-fg hover:bg-primary-hover focus-ring"
            >
              {t('orders.toCatalog')}
            </Link>
          }
        />
      ) : (
        <>
          <ul
            aria-label={t('orders.listLabel')}
            aria-busy={orders.isPlaceholderData || undefined}
            className="flex flex-col divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface shadow-soft dark:shadow-none"
          >
            {orders.data.items.map((order) => (
              <OrderRow key={order.id} order={order} />
            ))}
          </ul>
          {pageCount > 1 && (
            <Pagination
              className="self-center"
              page={page}
              pageCount={pageCount}
              hrefFor={(p) => (p === 1 ? '/orders' : `/orders?page=${p}`)}
              linkAs={RouterLink}
              labels={{
                nav: t('orders.pagination'),
                previous: t('catalog.previousPage'),
                next: t('catalog.nextPage'),
                page: (p) => t('catalog.page', { page: p }),
              }}
            />
          )}
        </>
      )}
    </div>
  )
}

function OrderRow({ order }: { order: OrderSummary }) {
  const { t } = useTranslation()
  const number = orderNumber(order.id)
  return (
    <li>
      <Link
        to={`/orders/${order.id}`}
        className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-4 py-4 transition-colors duration-150 ease-out hover:bg-surface-2 focus-ring sm:grid-cols-[minmax(0,1fr)_auto_auto_auto] sm:px-5"
        data-testid="order-row"
      >
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="font-heading font-bold text-text tabular">{number}</span>{' '}
          <span className="text-sm text-text-muted tabular">
            {formatDateTime(order.created_at)}
            {', '}
            {t('orders.itemsCount', { count: order.items_count })}
          </span>
        </div>{' '}
        <span className="row-start-2 justify-self-start sm:row-start-auto">
          <OrderStatusLabel status={order.status} />
        </span>{' '}
        <span className="row-span-2 font-heading text-lg font-extrabold text-text tabular sm:row-span-1">
          {formatPrice(order.total_tiyin)}
        </span>
        <ChevronRight
          aria-hidden="true"
          size={20}
          strokeWidth={1.75}
          className="hidden text-text-muted sm:block"
        />
      </Link>
    </li>
  )
}

function OrdersSkeleton() {
  const { t } = useTranslation()
  return (
    <div
      className="flex flex-col divide-y divide-border rounded-xl border border-border bg-surface"
      role="status"
      aria-busy="true"
      aria-label={t('common.loading')}
    >
      {Array.from({ length: 4 }, (_, i) => (
        <div key={i} className="flex items-center justify-between gap-4 px-4 py-4 sm:px-5">
          <div className="flex flex-col gap-2">
            <Skeleton className="h-5 w-28" />
            <Skeleton className="h-4 w-44" />
          </div>
          <Skeleton className="h-6 w-28" />
        </div>
      ))}
    </div>
  )
}
