import { CLIENT_ERROR, isApiError } from '@bozorcha/api-client'
import { Button, EmptyState } from '@bozorcha/ui'
import { RotateCw, Store, TriangleAlert, WifiOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'

type QueryErrorProps = {
  error: unknown
  onRetry: () => void
  retrying?: boolean
  className?: string
}

/**
 * Error state with a retry action, worded by failure type: network, server, or a seller whose
 * shop the catalog does not know yet (it is created right after approval).
 */
export function QueryError({ error, onRetry, retrying, className }: QueryErrorProps) {
  const { t } = useTranslation()
  const network = isApiError(error) && error.code === CLIENT_ERROR.NETWORK
  const shopPending = isApiError(error) && error.code === 'SELLER_NOT_FOUND'
  const Icon = network ? WifiOff : shopPending ? Store : TriangleAlert
  return (
    <EmptyState
      role="alert"
      tone={shopPending ? 'neutral' : 'danger'}
      className={className}
      icon={<Icon size={22} strokeWidth={1.75} />}
      title={shopPending ? t('errors.shopPendingTitle') : t('errors.title')}
      description={
        network ? t('errors.network') : shopPending ? t('errors.shopPending') : t('errors.server')
      }
      action={
        <Button
          variant="secondary"
          onClick={onRetry}
          loading={retrying}
          leadingIcon={<RotateCw aria-hidden="true" size={18} strokeWidth={1.75} />}
        >
          {t('common.retry')}
        </Button>
      }
    />
  )
}
