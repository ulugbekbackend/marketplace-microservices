import { useLogout } from '@bozorcha/api-client'
import { cn, useToast } from '@bozorcha/ui'
import { LogOut } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

/** Signs out (server revoke is best effort) and returns to the login page. */
export function LogoutButton({ className }: { className?: string }) {
  const { t } = useTranslation()
  const logout = useLogout()
  const { toast } = useToast()
  const navigate = useNavigate()
  return (
    <button
      type="button"
      disabled={logout.isPending}
      aria-label={t('header.logout')}
      onClick={() =>
        logout.mutate(undefined, {
          onSettled: () => {
            toast({ title: t('header.loggedOut'), tone: 'success' })
            navigate('/login', { replace: true })
          },
        })
      }
      className={cn(
        'inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-lg px-3 text-sm font-semibold text-text',
        'transition-colors duration-150 ease-out hover:bg-danger-soft hover:text-danger-ink focus-ring disabled:opacity-60',
        className,
      )}
    >
      <LogOut aria-hidden="true" size={20} strokeWidth={1.75} />
      <span className="hidden sm:inline">{t('header.logout')}</span>
    </button>
  )
}
