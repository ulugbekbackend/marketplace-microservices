import { cn } from '@bozorcha/ui'
import { Search } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate, useSearchParams } from 'react-router'

/** Submits to the catalog with `?q=` (keeps the current category when already in the catalog). */
export function SearchBox({ className }: { className?: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const id = useId()
  const current = params.get('q') ?? ''
  // Re-seed the field when the URL query changes (e.g. "clear search" in the catalog).
  const [draft, setDraft] = useState({ source: current, value: current })
  if (draft.source !== current) setDraft({ source: current, value: current })

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const q = draft.value.trim()
    const base = location.pathname.startsWith('/catalog') ? location.pathname : '/catalog'
    navigate(q ? `${base}?q=${encodeURIComponent(q)}` : base)
  }

  return (
    <form
      role="search"
      onSubmit={onSubmit}
      className={cn('relative flex w-full min-w-0', className)}
    >
      <label htmlFor={id} className="sr-only">
        {t('header.searchLabel')}
      </label>
      <input
        id={id}
        type="search"
        enterKeyHint="search"
        autoComplete="off"
        value={draft.value}
        onChange={(event) => setDraft({ source: current, value: event.target.value })}
        placeholder={t('header.searchPlaceholder')}
        className={cn(
          'h-11 w-full min-w-0 rounded-lg border border-border bg-surface-2 pr-12 pl-3 text-base text-text placeholder:text-text-muted',
          'transition-colors duration-150 ease-out hover:border-border-strong',
          'focus-visible:border-primary focus-visible:bg-surface focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-primary',
        )}
      />
      <button
        type="submit"
        aria-label={t('header.searchSubmit')}
        className="absolute inset-y-1 right-1 grid w-10 place-items-center rounded-md bg-primary text-primary-fg transition-colors duration-150 ease-out hover:bg-primary-hover focus-ring"
      >
        <Search aria-hidden="true" size={18} strokeWidth={1.75} />
      </button>
    </form>
  )
}
