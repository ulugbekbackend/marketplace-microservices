import type { OrderStatus, SubOrderStatus } from '@bozorcha/api-client'
import { Badge, OrderStatusBadge } from '@bozorcha/ui'
import { useTranslation } from 'react-i18next'
import { subOrderTone } from '../lib/orders'

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

export function SubOrderStatusLabel({ status }: { status: SubOrderStatus }) {
  const { t } = useTranslation()
  return (
    <Badge tone={subOrderTone(status)} dot data-status={status}>
      {t(`orders.subStatus.${status}`)}
    </Badge>
  )
}
