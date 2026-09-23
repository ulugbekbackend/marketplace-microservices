import type { ProductVariant } from '@bozorcha/api-client'
import { cn } from '@bozorcha/ui'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import {
  attributeGroups,
  optionState,
  selectOption,
  type OptionState,
  type Selection,
} from '../lib/variants'

type VariantSelectorProps = {
  variants: ProductVariant[]
  selection: Selection
  onChange: (selection: Selection) => void
}

const chipState: Record<OptionState, string> = {
  available: 'border-border bg-surface text-text hover:border-border-strong',
  incompatible: 'border-dashed border-border-strong bg-surface text-text-muted hover:text-text',
  unavailable:
    'cursor-not-allowed border-border bg-surface-2 text-text-muted line-through opacity-60',
}

/** One radio group per attribute; native radios give arrow-key navigation for free. */
export function VariantSelector({ variants, selection, onChange }: VariantSelectorProps) {
  const { t } = useTranslation()
  const baseId = useId()
  const groups = attributeGroups(variants)
  if (groups.length === 0) return null

  return (
    <div className="flex flex-col gap-4">
      {groups.map((group) => (
        <fieldset key={group.code} className="flex min-w-0 flex-col gap-2">
          <legend className="mb-2 text-sm text-text-muted">
            {group.name}:{' '}
            <span className="font-semibold text-text">{selection[group.code] ?? ''}</span>
          </legend>
          <div className="flex flex-wrap gap-2">
            {group.values.map((value) => {
              const state = optionState(variants, selection, group.code, value)
              const id = `${baseId}-${group.code}-${value}`
              const checked = selection[group.code] === value
              return (
                <div key={value} className="relative">
                  <input
                    id={id}
                    type="radio"
                    name={`${baseId}-${group.code}`}
                    value={value}
                    checked={checked}
                    disabled={state === 'unavailable'}
                    onChange={() => onChange(selectOption(variants, selection, group.code, value))}
                    className="peer sr-only"
                  />
                  <label
                    htmlFor={id}
                    className={cn(
                      'inline-flex h-10 min-w-10 cursor-pointer items-center justify-center rounded-lg border px-3 text-sm font-medium',
                      'transition-colors duration-150 ease-out',
                      'peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary',
                      chipState[state],
                      checked &&
                        'border-primary bg-primary-soft font-semibold text-primary no-underline',
                    )}
                  >
                    {value}
                    {state === 'unavailable' && (
                      <span className="sr-only">{`, ${t('product.outOfStock')}`}</span>
                    )}
                  </label>
                </div>
              )
            })}
          </div>
        </fieldset>
      ))}
    </div>
  )
}
