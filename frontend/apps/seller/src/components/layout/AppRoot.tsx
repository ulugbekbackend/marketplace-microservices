import { useToast } from '@bozorcha/ui'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, ScrollRestoration } from 'react-router'
import { onSessionExpired } from '../../lib/api'
import { useApplyTheme } from '../../lib/theme'

/** Root of every route: theme, session-expiry notice, skip link. */
export function AppRoot() {
  const { t } = useTranslation()
  const { toast } = useToast()
  useApplyTheme()

  useEffect(
    () => onSessionExpired(() => toast({ title: t('header.sessionExpired'), tone: 'info' })),
    [toast, t],
  )

  return (
    <>
      <a
        href="#main"
        className="sr-only z-[70] rounded-lg bg-primary px-4 py-2 font-semibold text-primary-fg focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        {t('common.skipToContent')}
      </a>
      <Outlet />
      <ScrollRestoration />
    </>
  )
}
