import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { cn } from '../lib/cn'

export type TabItem = {
  id: string
  label: ReactNode
  content: ReactNode
  disabled?: boolean
}

export type TabsProps = {
  items: TabItem[]
  /** Controlled selected tab id. */
  value?: string
  defaultValue?: string
  onValueChange?: (id: string) => void
  /** Accessible name for the tab list. */
  label: string
  className?: string
}

/** WAI-ARIA tabs with automatic activation and roving tabindex. */
export function Tabs({ items, value, defaultValue, onValueChange, label, className }: TabsProps) {
  const baseId = useId()
  const [internal, setInternal] = useState(defaultValue ?? items[0]?.id)
  const selected = value ?? internal
  const tabRefs = useRef(new Map<string, HTMLButtonElement>())

  const select = (id: string) => {
    if (value === undefined) setInternal(id)
    onValueChange?.(id)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const enabled = items.filter((item) => !item.disabled)
    const index = enabled.findIndex((item) => item.id === selected)
    let next: TabItem | undefined
    if (event.key === 'ArrowRight') next = enabled[(index + 1) % enabled.length]
    else if (event.key === 'ArrowLeft')
      next = enabled[(index - 1 + enabled.length) % enabled.length]
    else if (event.key === 'Home') next = enabled[0]
    else if (event.key === 'End') next = enabled[enabled.length - 1]
    if (!next) return
    event.preventDefault()
    select(next.id)
    tabRefs.current.get(next.id)?.focus()
  }

  return (
    <div className={className}>
      <div
        role="tablist"
        aria-label={label}
        className="flex gap-1 overflow-x-auto border-b border-border"
      >
        {items.map((item) => {
          const isSelected = item.id === selected
          return (
            <button
              key={item.id}
              ref={(node) => {
                if (node) tabRefs.current.set(item.id, node)
                else tabRefs.current.delete(item.id)
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${item.id}`}
              aria-selected={isSelected}
              aria-controls={`${baseId}-panel-${item.id}`}
              tabIndex={isSelected ? 0 : -1}
              disabled={item.disabled}
              onClick={() => select(item.id)}
              onKeyDown={onKeyDown}
              className={cn(
                '-mb-px h-11 shrink-0 border-b-2 px-3 text-sm font-semibold whitespace-nowrap transition-colors duration-150 ease-out focus-ring',
                isSelected
                  ? 'border-primary text-primary'
                  : 'border-transparent text-text-muted hover:text-text',
                'disabled:cursor-not-allowed disabled:opacity-50',
              )}
            >
              {item.label}
            </button>
          )
        })}
      </div>
      {items.map((item) => (
        <div
          key={item.id}
          role="tabpanel"
          id={`${baseId}-panel-${item.id}`}
          aria-labelledby={`${baseId}-tab-${item.id}`}
          hidden={item.id !== selected}
          tabIndex={0}
          className="pt-4 focus-ring"
        >
          {item.id === selected && item.content}
        </div>
      ))}
    </div>
  )
}
