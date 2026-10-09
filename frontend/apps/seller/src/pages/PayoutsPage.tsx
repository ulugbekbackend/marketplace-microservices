import { useSellerPayouts, type SellerPayout } from '@bozorcha/api-client'
import {
  Badge,
  DataTable,
  EmptyState,
  formatPrice,
  Pagination,
  type DataTableColumn,
} from '@bozorcha/ui'
import { Wallet } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { QueryError } from '../components/QueryError'
import { RouterLink } from '../components/RouterLink'
import { PAYOUTS_PAGE_SIZE, payoutWeek, payoutWeekShort, readPage } from '../lib/payouts'

const STATUS_TONE = { pending: 'info', paid: 'success' } as const

export function PayoutsPage() {
  const { t } = useTranslation()
  const [params] = useSearchParams()
  const page = readPage(params)
  const payouts = useSellerPayouts({ page, page_size: PAYOUTS_PAGE_SIZE })

  const total = payouts.data?.total ?? 0
  const pageCount = Math.ceil(total / (payouts.data?.page_size ?? PAYOUTS_PAGE_SIZE))
  const hrefFor = (target: number) => (target === 1 ? '/payouts' : `/payouts?page=${target}`)

  const columns: DataTableColumn<SellerPayout>[] = [
    {
      id: 'week',
      header: t('payouts.week'),
      className: 'whitespace-nowrap tabular',
      cell: (payout) => (
        <div className="flex flex-col gap-0.5">
          <span className="hidden font-semibold text-text sm:inline">
            {t('payouts.weekValue', payoutWeek(payout.period_start, payout.period_end))}
          </span>
          <span className="font-semibold text-text sm:hidden">
            {payoutWeekShort(payout.period_start, payout.period_end)}
          </span>
          <span className="text-xs text-text-muted sm:hidden">
            {t('payouts.ordersCountLong', { count: payout.lines_count })}
          </span>
        </div>
      ),
    },
    {
      id: 'orders',
      header: t('payouts.orders'),
      align: 'end',
      className: 'hidden sm:table-cell whitespace-nowrap tabular',
      cell: (payout) => t('payouts.ordersCount', { count: payout.lines_count }),
    },
    {
      id: 'gross',
      header: t('payouts.gross'),
      align: 'end',
      className: 'hidden md:table-cell whitespace-nowrap tabular text-text-muted',
      cell: (payout) => formatPrice(payout.gross_tiyin),
    },
    {
      id: 'commission',
      header: t('payouts.commission'),
      align: 'end',
      className: 'hidden md:table-cell whitespace-nowrap tabular text-text-muted',
      cell: (payout) => `−${formatPrice(payout.commission_tiyin)}`,
    },
    {
      id: 'net',
      header: t('payouts.net'),
      align: 'end',
      className: 'whitespace-nowrap tabular',
      cell: (payout) => (
        <div className="flex flex-col items-end gap-1">
          <span className="font-heading text-base font-extrabold text-text">
            {formatPrice(payout.net_tiyin)}
          </span>
          <span className="sm:hidden">
            <PayoutStatus payout={payout} />
          </span>
        </div>
      ),
    },
    {
      id: 'status',
      header: t('payouts.status'),
      className: 'hidden sm:table-cell',
      cell: (payout) => <PayoutStatus payout={payout} />,
    },
  ]

  return (
    <div className="page-container flex flex-col gap-5 py-6 sm:py-8">
      <title>{`${t('payouts.pageTitle')} | ${t('common.panel')}`}</title>
      <div className="flex max-w-2xl flex-col gap-1">
        <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text sm:text-3xl">
          {t('payouts.pageTitle')}
        </h1>
        <p className="text-sm text-text-muted">{t('payouts.intro')}</p>
        {payouts.data && total > 0 && (
          <p className="text-sm text-text-muted tabular">{t('payouts.total', { count: total })}</p>
        )}
      </div>

      {payouts.isError ? (
        <QueryError
          error={payouts.error}
          onRetry={() => void payouts.refetch()}
          retrying={payouts.isFetching}
        />
      ) : (
        <div className="flex flex-col gap-4">
          <DataTable
            caption={t('payouts.tableCaption')}
            columns={columns}
            rows={payouts.data?.items}
            getRowId={(payout) => payout.id}
            loading={payouts.isPending}
            stale={payouts.isPlaceholderData}
            empty={
              <EmptyState
                icon={<Wallet size={22} strokeWidth={1.75} />}
                title={t('payouts.empty')}
                description={t('payouts.emptyHint')}
              />
            }
          />
          <Pagination
            page={page}
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
      )}
    </div>
  )
}

function PayoutStatus({ payout }: { payout: SellerPayout }) {
  const { t } = useTranslation()
  const status = payout.status === 'paid' ? 'paid' : 'pending'
  return (
    <Badge tone={STATUS_TONE[status]} dot>
      {t(`payouts.statusValue.${status}`)}
    </Badge>
  )
}
