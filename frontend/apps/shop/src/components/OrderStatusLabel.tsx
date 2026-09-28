import type { OrderStatus, SubOrderStatus } from '@bozorcha/api-client'
import { OrderStatusBadge } from '@bozorcha/ui'
import { useTranslation } from 'react-i18next'

export function OrderStatusLabel({
  status,
  className,
}: {
  status: OrderStatus
  className?: string
}) {
  const { t } = useTranslation()
  return (
    <OrderStatusBadge status={status} className={className}>
      {t(`orders.status.${status}`)}
    </OrderStatusBadge>
  )
}

/** Same shared colours (ui ORDER_STATUS_TONE) the seller sees for this sub-order. */
export function SubOrderStatusLabel({ status }: { status: SubOrderStatus }) {
  const { t } = useTranslation()
  return <OrderStatusBadge status={status}>{t(`orders.subStatus.${status}`)}</OrderStatusBadge>
}
