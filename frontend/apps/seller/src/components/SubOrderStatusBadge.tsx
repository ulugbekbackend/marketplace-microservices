import type { SubOrderStatus } from '@bozorcha/api-client'
import { OrderStatusBadge } from '@bozorcha/ui'
import { useTranslation } from 'react-i18next'

/** Shared status colours (ui `ORDER_STATUS_TONE`), the same as the shop shows the customer. */
export function SubOrderStatusBadge({
  status,
  className,
}: {
  status: SubOrderStatus
  className?: string
}) {
  const { t } = useTranslation()
  return (
    <OrderStatusBadge status={status} className={className}>
      {t(`subOrderStatus.${status}`)}
    </OrderStatusBadge>
  )
}
