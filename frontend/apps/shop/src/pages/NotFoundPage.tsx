import { Button, EmptyState } from '@bozorcha/ui'
import { MapPinOff, RotateCw, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

/** Full-page "not found" used for unknown routes and missing products/shops. */
export function NotFoundPage({ title, description }: { title?: string; description?: string }) {
  const { t } = useTranslation()
  return (
    <PageMessage>
      <title>{`${title ?? t('errors.notFoundTitle')} | ${t('common.brand')}`}</title>
      <EmptyState
        icon={<MapPinOff size={22} strokeWidth={1.75} />}
        title={title ?? t('errors.notFoundTitle')}
        description={description ?? t('errors.notFoundHint')}
        action={
          <Link
            to="/"
            className="inline-flex h-11 items-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-fg hover:bg-primary-hover focus-ring"
          >
            {t('common.backHome')}
          </Link>
        }
      />
    </PageMessage>
  )
}

/** Rendered by the router when a page throws while rendering. */
export function RouteErrorPage() {
  const { t } = useTranslation()
  return (
    <PageMessage>
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
    </PageMessage>
  )
}

function PageMessage({ children }: { children: ReactNode }) {
  return <div className="page-container py-12 sm:py-16">{children}</div>
}
