import { useLogout, useMe, useSession } from '@bozorcha/api-client'
import { Badge, cn, Skeleton, useToast } from '@bozorcha/ui'
import { LogOut, UserRound } from 'lucide-react'
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate } from 'react-router'
import { formatE164 } from '../../lib/phone'

/** Login link for guests; for signed-in users a menu button with profile info and logout. */
export function AccountMenu() {
  const { t } = useTranslation()
  const { isAuthenticated } = useSession()
  const location = useLocation()

  if (!isAuthenticated) {
    if (location.pathname === '/login') return null
    const next = encodeURIComponent(`${location.pathname}${location.search}`)
    return (
      <Link
        to={`/login?next=${next}`}
        className="inline-flex h-11 shrink-0 items-center gap-2 rounded-lg px-3 text-sm font-semibold text-text transition-colors duration-150 ease-out hover:bg-surface-2 focus-ring"
      >
        <UserRound aria-hidden="true" size={20} strokeWidth={1.75} />
        <span>{t('header.login')}</span>
      </Link>
    )
  }
  return <SignedInMenu />
}

function SignedInMenu() {
  const { t } = useTranslation()
  const { data: me, isPending } = useMe()
  const logout = useLogout()
  const { toast } = useToast()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const menuId = useId()
  const buttonRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  const close = (restoreFocus = true) => {
    setOpen(false)
    if (restoreFocus) buttonRef.current?.focus()
  }

  useEffect(() => {
    if (!open) return
    menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (!menuRef.current?.contains(target) && !buttonRef.current?.contains(target)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  const onMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(
      menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [],
    )
    const index = items.indexOf(document.activeElement as HTMLElement)
    if (event.key === 'Escape') {
      event.preventDefault()
      close()
    } else if (event.key === 'ArrowDown') {
      event.preventDefault()
      items[(index + 1) % items.length]?.focus()
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      items[(index - 1 + items.length) % items.length]?.focus()
    } else if (event.key === 'Tab') {
      close(false)
    }
  }

  const onLogout = () => {
    close(false)
    logout.mutate(undefined, {
      onSettled: () => {
        toast({ title: t('header.loggedOut'), tone: 'success' })
        navigate('/')
      },
    })
  }

  const displayName = me?.full_name?.trim() || (me ? formatE164(me.phone) : '')
  const initial = (me?.full_name?.trim()?.[0] ?? me?.phone.slice(-2) ?? '').toUpperCase()

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={t('header.account')}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' && !open) {
            event.preventDefault()
            setOpen(true)
          }
        }}
        className="grid size-11 shrink-0 place-items-center rounded-lg transition-colors duration-150 ease-out hover:bg-surface-2 focus-ring"
      >
        <span
          aria-hidden="true"
          className="grid size-8 place-items-center rounded-full bg-primary text-sm font-bold text-primary-fg tabular"
        >
          {initial || <UserRound size={18} strokeWidth={1.75} />}
        </span>
      </button>
      {open && (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label={t('header.account')}
          tabIndex={-1}
          onKeyDown={onMenuKeyDown}
          className="absolute top-full right-0 z-50 mt-2 w-64 max-w-[calc(100vw-2rem)] animate-fade-in rounded-xl border border-border bg-surface p-1.5 shadow-soft"
        >
          <div className="border-b border-border px-3 pt-2 pb-3" role="none">
            {isPending ? (
              <div className="flex flex-col gap-2" aria-hidden="true">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-20" />
              </div>
            ) : (
              <>
                <p className="truncate font-semibold text-text">{displayName}</p>
                {me?.full_name && (
                  <p className="text-sm text-text-muted tabular">{formatE164(me.phone)}</p>
                )}
                {me && (
                  <Badge tone="primary" className="mt-2">
                    {t(`header.roles.${me.role}`)}
                  </Badge>
                )}
              </>
            )}
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={onLogout}
            disabled={logout.isPending}
            className={cn(
              'mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm font-medium text-danger-ink',
              'transition-colors duration-150 ease-out hover:bg-danger-soft focus:bg-danger-soft focus:outline-none',
            )}
          >
            <LogOut aria-hidden="true" size={18} strokeWidth={1.75} />
            {t('header.logout')}
          </button>
        </div>
      )}
    </div>
  )
}
