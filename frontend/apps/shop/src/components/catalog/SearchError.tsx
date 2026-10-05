import { isApiError } from '@bozorcha/api-client'
import { Button, EmptyState } from '@bozorcha/ui'
import { RotateCw, SearchX } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { QueryError } from '../QueryError'

/** 503 from the search service gets its own wording; everything else the generic error. */
export function SearchError({
  error,
  onRetry,
  retrying,
}: {
  error: unknown
  onRetry: () => void
  retrying?: boolean
}) {
  const { t } = useTranslation()
  if (isApiError(error) && (error.status === 503 || error.code === 'SEARCH_UNAVAILABLE')) {
    return (
      <EmptyState
        role="alert"
        tone="danger"
        icon={<SearchX size={22} strokeWidth={1.75} />}
        title={t('catalog.unavailableTitle')}
        description={t('catalog.unavailableHint')}
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
  return <QueryError error={error} onRetry={onRetry} retrying={retrying} />
}
