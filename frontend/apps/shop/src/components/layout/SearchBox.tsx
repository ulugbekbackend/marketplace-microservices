import { SUGGEST_MIN_LENGTH, useSuggest, type Suggestion } from '@bozorcha/api-client'
import { cn } from '@bozorcha/ui'
import { Search } from 'lucide-react'
import { useId, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router'
import { useDebouncedValue } from '../../lib/useDebouncedValue'

/** Typing pause before suggestions are requested. */
export const SUGGEST_DEBOUNCE_MS = 200

/**
 * Header search with suggestions (WAI-ARIA combobox with a listbox popup). Enter searches the
 * whole catalog (`/catalog?q=`); picking a suggestion opens that product. Arrow keys move
 * through the list, Escape closes it (a second Escape clears the field).
 */
export function SearchBox({ className }: { className?: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const id = useId()
  const listId = `${id}-list`
  const current = params.get('q') ?? ''
  // Re-seed the field when the URL query changes (e.g. "clear search" in the catalog).
  const [draft, setDraft] = useState({ source: current, value: current })
  if (draft.source !== current) setDraft({ source: current, value: current })
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)

  const term = useDebouncedValue(draft.value.trim(), SUGGEST_DEBOUNCE_MS)
  const suggest = useSuggest(term)
  const typed = draft.value.trim()
  const items: Suggestion[] = typed.length >= SUGGEST_MIN_LENGTH ? (suggest.data ?? []) : []
  const expanded = open && items.length > 0
  const activeItem = expanded && active >= 0 ? items[active] : undefined

  const setValue = (value: string) => {
    setDraft({ source: current, value })
    setActive(-1)
    setOpen(true)
  }

  const close = () => {
    setOpen(false)
    setActive(-1)
  }

  const pick = (item: Suggestion) => {
    close()
    setDraft({ source: current, value: '' })
    navigate(`/p/${encodeURIComponent(item.slug)}`)
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (activeItem) {
      pick(activeItem)
      return
    }
    close()
    navigate(typed ? `/catalog?q=${encodeURIComponent(typed)}` : '/catalog')
  }

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    switch (event.key) {
      case 'ArrowDown':
      case 'ArrowUp': {
        if (items.length === 0) return
        event.preventDefault()
        const step = event.key === 'ArrowDown' ? 1 : -1
        setOpen(true)
        // From the field the first press lands on the first (or last) option; wraps around.
        setActive((index) =>
          !expanded || index < 0
            ? step === 1
              ? 0
              : items.length - 1
            : (index + step + items.length) % items.length,
        )
        return
      }
      case 'Escape':
        if (expanded) {
          event.preventDefault()
          close()
        } else if (draft.value) {
          event.preventDefault()
          setDraft({ source: current, value: '' })
        }
        return
      case 'Tab':
        close()
        return
    }
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
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-activedescendant={activeItem ? `${listId}-${active}` : undefined}
        enterKeyHint="search"
        autoComplete="off"
        spellCheck={false}
        value={draft.value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        onFocus={() => setOpen(true)}
        onBlur={close}
        placeholder={t('header.searchPlaceholder')}
        className={cn(
          'h-11 w-full min-w-0 rounded-lg border border-border bg-surface-2 pr-12 pl-3 text-base text-text placeholder:text-text-muted',
          'transition-colors duration-150 ease-out hover:border-border-strong',
          'focus-visible:border-primary focus-visible:bg-surface focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-primary',
          '[&::-webkit-search-cancel-button]:hidden',
        )}
      />
      <button
        type="submit"
        aria-label={t('header.searchSubmit')}
        className="absolute inset-y-1 right-1 grid w-10 place-items-center rounded-md bg-primary text-primary-fg transition-colors duration-150 ease-out hover:bg-primary-hover focus-ring"
      >
        <Search aria-hidden="true" size={18} strokeWidth={1.75} />
      </button>
      <ul
        id={listId}
        role="listbox"
        aria-label={t('header.suggestions')}
        hidden={!expanded}
        className="absolute inset-x-0 top-full z-50 mt-1.5 overflow-hidden rounded-xl border border-border bg-surface py-1.5 shadow-soft dark:shadow-none"
      >
        {items.map((item, index) => (
          // Options never take focus: the field handles the keys and points at the active
          // option with aria-activedescendant (WAI-ARIA combobox pattern).
          // eslint-disable-next-line jsx-a11y/click-events-have-key-events
          <li
            key={item.id}
            id={`${listId}-${index}`}
            role="option"
            aria-selected={index === active}
            // Keep focus in the field: the click must not blur it before it lands.
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => pick(item)}
            onMouseMove={() => index !== active && setActive(index)}
            className={cn(
              'flex min-h-11 cursor-pointer items-center gap-3 px-3 py-2 text-sm text-text',
              index === active && 'bg-surface-2',
            )}
          >
            <Search
              aria-hidden="true"
              size={16}
              strokeWidth={1.75}
              className="shrink-0 text-text-muted"
            />
            <span className="min-w-0 truncate">
              <Highlight text={item.title} query={typed} />
            </span>
          </li>
        ))}
      </ul>
      <p role="status" className="sr-only">
        {expanded ? t('header.suggestionsCount', { count: items.length }) : ''}
      </p>
    </form>
  )
}

/** The typed part of a suggestion in bold, when it matches as written (same script). */
function Highlight({ text, query }: { text: string; query: string }) {
  const at = query ? text.toLocaleLowerCase('uz').indexOf(query.toLocaleLowerCase('uz')) : -1
  if (at < 0) return <>{text}</>
  return (
    <>
      {text.slice(0, at)}
      <strong className="font-semibold">{text.slice(at, at + query.length)}</strong>
      {text.slice(at + query.length)}
    </>
  )
}
