import { useMe } from '@bozorcha/api-client'
import { Skeleton } from '@bozorcha/ui'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate } from 'react-router'
import { QueryError } from './QueryError'

/** The panel is for sellers only; everyone else goes to the seller application. */
export function RequireSeller({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const me = useMe()
  if (me.isPending) {
    return (
      <div className="flex min-h-dvh" aria-busy="true" aria-label={t('common.loading')}>
        <div className="hidden w-64 border-r border-border bg-surface p-4 lg:block">
          <Skeleton className="h-7 w-32" />
          <div className="mt-8 flex flex-col gap-2">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        </div>
        <div className="flex-1 p-4 sm:p-6">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="mt-6 h-64 w-full" />
        </div>
      </div>
    )
  }
  if (me.isError) {
    return (
      <div className="page-container py-12">
        <QueryError error={me.error} onRetry={() => void me.refetch()} retrying={me.isFetching} />
      </div>
    )
  }
  if (me.data.role !== 'seller') return <Navigate to="/onboarding" replace />
  return children
}
