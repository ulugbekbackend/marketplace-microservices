import { CLIENT_ERROR, isApiError } from '@bozorcha/api-client'
import { Button, EmptyState } from '@bozorcha/ui'
import { RotateCw, WifiOff, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'

type QueryErrorProps = {
  error: unknown
  onRetry: () => void
  retrying?: boolean
  className?: string
}

/** Error state with a retry action, worded by failure type (network vs server). */
export function QueryError({ error, onRetry, retrying, className }: QueryErrorProps) {
  const { t } = useTranslation()
  const network = isApiError(error) && error.code === CLIENT_ERROR.NETWORK
  return (
    <EmptyState
      role="alert"
      tone="danger"
      className={className}
      icon={
        network ? (
          <WifiOff size={22} strokeWidth={1.75} />
        ) : (
          <TriangleAlert size={22} strokeWidth={1.75} />
        )
      }
      title={t('errors.title')}
      description={network ? t('errors.network') : t('errors.server')}
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
