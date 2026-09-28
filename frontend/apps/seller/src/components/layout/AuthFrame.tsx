import { useSession } from '@bozorcha/api-client'
import { Wordmark } from '@bozorcha/ui'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { LogoutButton } from './LogoutButton'
import { ThemeToggle } from './ThemeToggle'

/** Chrome for pages outside the panel (login, seller application). */
export function AuthFrame({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const { isAuthenticated } = useSession()
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-border bg-surface">
        <div aria-hidden="true" className="awning h-1 w-full" />
        <div className="page-container flex h-16 items-center gap-2">
          <span className="flex items-baseline gap-2">
            <Wordmark className="text-xl" />
            <span className="text-sm font-semibold text-text-muted">{t('common.seller')}</span>
          </span>
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            {isAuthenticated && <LogoutButton />}
          </div>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="flex-1 outline-none">
        {children}
      </main>
    </div>
  )
}
