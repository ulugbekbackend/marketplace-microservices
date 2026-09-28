import { useSellerOrders, useSellerOrderStats, type SellerSubOrder } from '@bozorcha/api-client'
import {
  Button,
  DataTable,
  EmptyState,
  formatPrice,
  Input,
  Pagination,
  Tabs,
  type DataTableColumn,
} from '@bozorcha/ui'
import { ClipboardList, SearchX, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import { QueryError } from '../components/QueryError'
import { RouterLink } from '../components/RouterLink'
import { SubOrderStatusBadge } from '../components/SubOrderStatusBadge'
import { formatDateTime } from '../lib/dates'
import {
  ORDERS_PAGE_SIZE,
  orderNumber,
  readOrdersFilter,
  SUB_ORDER_STATUSES,
  toListParams,
  withParam,
  type OrdersTab,
} from '../lib/orders'
import { totalCount } from '../lib/stats'

const TABS: OrdersTab[] = ['all', ...SUB_ORDER_STATUSES]

export function OrdersPage() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const filter = readOrdersFilter(params)
  const orders = useSellerOrders(toListParams(filter))
  const stats = useSellerOrderStats()
  const counts = stats.data?.by_status

  const setParam = (key: string, value: string | null) =>
    setParams((current) => withParam(current, key, value))

  const hrefFor = (target: number) => {
    const next = withParam(params, 'page', target === 1 ? null : String(target))
    const query = next.toString()
    return `/orders${query ? `?${query}` : ''}`
  }

  const tabLabel = (tab: OrdersTab) => {
    const label = tab === 'all' ? t('orders.all') : t(`subOrderStatus.${tab}`)
    const count = counts ? (tab === 'all' ? totalCount(counts) : counts[tab]) : undefined
    return (
      <span className="flex items-center gap-2">
        {label}
        {count !== undefined && (
          <span
            className="relative min-w-6 rounded-full bg-surface-2 px-1.5 text-center text-xs leading-5 font-semibold text-text-muted tabular"
            data-testid={`tab-count-${tab}`}
          >
            <span className="sr-only">, </span>
            {count}
          </span>
        )}
      </span>
    )
  }

  const columns: DataTableColumn<SellerSubOrder>[] = [
    {
      id: 'number',
      header: t('orders.number'),
      cell: (order) => (
        <div className="flex min-w-0 flex-col gap-0.5">
          <Link
            to={`/orders/${order.id}`}
            className="rounded-sm font-semibold whitespace-nowrap text-text tabular hover:text-primary hover:underline focus-ring"
          >
            {t('orders.numberValue', { number: orderNumber(order.order_id) })}
          </Link>
          <span className="text-xs text-text-muted tabular md:hidden">
            {formatDateTime(order.created_at)}
          </span>
          <span className="max-w-40 truncate text-xs text-text-muted sm:hidden">
            {order.customer_name}
          </span>
        </div>
      ),
    },
    {
      id: 'date',
      header: t('orders.date'),
      className: 'hidden md:table-cell whitespace-nowrap tabular text-text-muted',
      cell: (order) => formatDateTime(order.created_at),
    },
    {
      id: 'customer',
      header: t('orders.customer'),
      className: 'hidden sm:table-cell',
      cell: (order) => (
        <div className="flex min-w-0 flex-col">
          <span className="max-w-48 truncate text-text">{order.customer_name}</span>
          <span className="text-xs text-text-muted">{order.city}</span>
        </div>
      ),
    },
    {
      id: 'items',
      header: t('orders.items'),
      align: 'end',
      className: 'hidden lg:table-cell whitespace-nowrap tabular',
      cell: (order) => t('orders.itemsCount', { count: order.items_count }),
    },
    {
      id: 'amount',
      header: t('orders.amount'),
      align: 'end',
      className: 'whitespace-nowrap tabular',
      cell: (order) => (
        <div className="flex flex-col items-end gap-1">
          <span className="font-semibold text-text">{formatPrice(order.subtotal_tiyin)}</span>
          <span className="hidden text-xs text-text-muted sm:block">
            {t('orders.netShort', { amount: formatPrice(order.net_tiyin) })}
          </span>
          <span className="sm:hidden">
            <SubOrderStatusBadge status={order.status} />
          </span>
        </div>
      ),
    },
    {
      id: 'status',
      header: t('orders.status'),
      className: 'hidden sm:table-cell',
      cell: (order) => <SubOrderStatusBadge status={order.status} />,
    },
  ]

  const filtered = filter.tab !== 'all' || Boolean(filter.from || filter.to)
  const emptyState = filtered ? (
    <EmptyState
      icon={<SearchX size={22} strokeWidth={1.75} />}
      title={t('orders.notFound')}
      description={t('orders.notFoundHint')}
      action={
        <Button variant="secondary" onClick={() => setParams(new URLSearchParams())}>
          {t('orders.clearFilters')}
        </Button>
      }
    />
  ) : (
    <EmptyState
      icon={<ClipboardList size={22} strokeWidth={1.75} />}
      title={t('orders.empty')}
      description={t('orders.emptyHint')}
    />
  )

  const total = orders.data?.total ?? 0
  const pageCount = Math.ceil(total / (orders.data?.page_size ?? ORDERS_PAGE_SIZE))

  const listing = orders.isError ? (
    <QueryError
      error={orders.error}
      onRetry={() => void orders.refetch()}
      retrying={orders.isFetching}
    />
  ) : (
    <div className="flex flex-col gap-4">
      <DataTable
        caption={t('orders.tableCaption')}
        columns={columns}
        rows={orders.data?.items}
        getRowId={(order) => order.id}
        loading={orders.isPending}
        stale={orders.isPlaceholderData}
        empty={emptyState}
      />
      <Pagination
        page={filter.page}
        pageCount={pageCount}
        hrefFor={hrefFor}
        linkAs={RouterLink}
        labels={{
          nav: t('pagination.nav'),
          previous: t('pagination.previous'),
          next: t('pagination.next'),
          page: (n) => t('pagination.page', { page: n }),
        }}
      />
    </div>
  )

  return (
    <div className="page-container flex flex-col gap-5 py-6 sm:py-8">
      <title>{`${t('orders.pageTitle')} | ${t('common.panel')}`}</title>
      <div>
        <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text sm:text-3xl">
          {t('orders.pageTitle')}
        </h1>
        {orders.data && (
          <p className="mt-1 text-sm text-text-muted tabular">
            {t('orders.total', { count: total })}
          </p>
        )}
      </div>

      <fieldset className="flex flex-wrap items-end gap-3">
        <legend className="sr-only">{t('orders.datesLabel')}</legend>
        <Input
          type="date"
          label={t('orders.dateFrom')}
          value={filter.from ?? ''}
          max={filter.to ?? undefined}
          onChange={(event) => setParam('from', event.target.value || null)}
          wrapperClassName="w-full min-[400px]:w-44"
        />
        <Input
          type="date"
          label={t('orders.dateTo')}
          value={filter.to ?? ''}
          min={filter.from ?? undefined}
          onChange={(event) => setParam('to', event.target.value || null)}
          wrapperClassName="w-full min-[400px]:w-44"
        />
        {(filter.from || filter.to) && (
          <Button
            variant="ghost"
            onClick={() =>
              setParams((current) => withParam(withParam(current, 'from', null), 'to', null))
            }
            leadingIcon={<X aria-hidden="true" size={18} strokeWidth={1.75} />}
          >
            {t('orders.clearDates')}
          </Button>
        )}
      </fieldset>

      <Tabs
        label={t('orders.filterLabel')}
        value={filter.tab}
        onValueChange={(tab) => setParam('status', tab === 'all' ? null : tab)}
        items={TABS.map((id) => ({ id, label: tabLabel(id), content: listing }))}
      />
    </div>
  )
}
