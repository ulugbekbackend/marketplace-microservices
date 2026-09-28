import type { ProductStatus } from '@bozorcha/api-client'
import { Badge, type BadgeTone } from '@bozorcha/ui'
import { useTranslation } from 'react-i18next'

const TONE: Record<ProductStatus, BadgeTone> = {
  draft: 'neutral',
  active: 'success',
  archived: 'muted',
}

export function ProductStatusBadge({ status = 'draft' }: { status?: ProductStatus }) {
  const { t } = useTranslation()
  return (
    <Badge tone={TONE[status]} dot data-status={status}>
      {t(`productStatus.${status}`)}
    </Badge>
  )
}
