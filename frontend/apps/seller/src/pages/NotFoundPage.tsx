import { Button, EmptyState } from '@bozorcha/ui'
import { MapPinOff, RotateCw, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

export function NotFoundPage() {
  const { t } = useTranslation()
  return (
    <div className="page-container py-12 sm:py-16">
      <title>{`${t('errors.notFoundTitle')} | ${t('common.panel')}`}</title>
      <EmptyState
        icon={<MapPinOff size={22} strokeWidth={1.75} />}
        title={t('errors.notFoundTitle')}
        description={t('errors.notFoundHint')}
        action={
          <Link
            to="/"
            className="inline-flex h-11 items-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-fg hover:bg-primary-hover focus-ring"
          >
            {t('errors.backToPanel')}
          </Link>
        }
      />
    </div>
  )
}

/** Rendered by the router when a page throws while rendering. */
export function RouteErrorPage() {
  const { t } = useTranslation()
  return (
    <div className="page-container py-12 sm:py-16">
      <EmptyState
        role="alert"
        tone="danger"
        icon={<TriangleAlert size={22} strokeWidth={1.75} />}
        title={t('errors.crashTitle')}
        description={t('errors.crashHint')}
        action={
          <Button
            onClick={() => window.location.reload()}
            leadingIcon={<RotateCw aria-hidden="true" size={18} strokeWidth={1.75} />}
          >
            {t('errors.reload')}
          </Button>
        }
      />
    </div>
  )
}
