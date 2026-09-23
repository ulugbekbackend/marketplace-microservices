import { useToast, Wordmark } from '@bozorcha/ui'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, ScrollRestoration } from 'react-router'
import { onSessionExpired } from '../../lib/api'
import { useApplyTheme } from '../../lib/theme'
import { Header } from './Header'

export function AppShell() {
  const { t } = useTranslation()
  const { toast } = useToast()
  useApplyTheme()

  useEffect(
    () => onSessionExpired(() => toast({ title: t('header.sessionExpired'), tone: 'info' })),
    [toast, t],
  )

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only z-50 rounded-lg bg-primary px-4 py-2 font-semibold text-primary-fg focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        {t('common.skipToContent')}
      </a>
      <Header />
      <main id="main" tabIndex={-1} className="flex-1 outline-none">
        <Outlet />
      </main>
      <Footer />
      <ScrollRestoration />
    </div>
  )
}

function Footer() {
  const { t } = useTranslation()
  return (
    <footer className="mt-16 border-t border-border bg-surface">
      <div className="page-container flex flex-col gap-2 py-8 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1">
          <Wordmark className="text-xl" />
          <p className="text-sm text-text-muted">{t('footer.tagline')}</p>
        </div>
        <p className="text-sm text-text-muted tabular">
          {t('footer.rights', { year: new Date().getFullYear() })}
        </p>
      </div>
    </footer>
  )
}
