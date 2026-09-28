import type { Attribute } from '@bozorcha/api-client'
import { Badge, Button, cn, Select } from '@bozorcha/ui'
import { Check, Lock, Plus, RotateCcw, Trash2, X } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { normalizeSomInput } from '../lib/money'
import type { FieldError, RowErrors } from '../lib/productForm'
import {
  lockedValueIds,
  syncRows,
  type AttributeSelection,
  type VariantRow,
} from '../lib/variantMatrix'

export type MatrixState = { selection: AttributeSelection[]; rows: VariantRow[] }

type VariantMatrixProps = {
  attributes: Attribute[]
  state: MatrixState
  onChange: (state: MatrixState) => void
  skuBase: string
  errors: Record<string, RowErrors>
  formError: FieldError | null
}

const inputClass = cn(
  'h-10 w-full min-w-0 rounded-lg border border-border bg-surface-2 px-2.5 text-sm text-text tabular',
  'transition-colors duration-150 ease-out hover:border-border-strong placeholder:text-text-muted',
  'focus-visible:border-primary focus-visible:bg-surface focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-primary',
  'aria-[invalid=true]:border-danger disabled:opacity-60',
)

/**
 * Pick attributes and their values; every combination becomes a variant row with SKU, price
 * and stock. Values used by saved variants are locked: those variants can only be deactivated.
 */
export function VariantMatrix({
  attributes,
  state,
  onChange,
  skuBase,
  errors,
  formError,
}: VariantMatrixProps) {
  const { t } = useTranslation()
  const [adding, setAdding] = useState('')
  const locked = lockedValueIds(state.rows)
  const selectedIds = new Set(state.selection.map((item) => item.attributeId))
  const available = attributes.filter((attribute) => !selectedIds.has(attribute.id))
  const byId = new Map(attributes.map((attribute) => [attribute.id, attribute]))

  const setSelection = (selection: AttributeSelection[]) =>
    onChange({ selection, rows: syncRows(state.rows, selection, attributes, skuBase) })

  const toggleValue = (attributeId: string, valueId: string) =>
    setSelection(
      state.selection.map((item) =>
        item.attributeId !== attributeId
          ? item
          : {
              ...item,
              valueIds: item.valueIds.includes(valueId)
                ? item.valueIds.filter((id) => id !== valueId)
                : [...item.valueIds, valueId],
            },
      ),
    )

  const updateRow = (key: string, change: Partial<VariantRow>) =>
    onChange({
      ...state,
      rows: state.rows.map((row) => (row.key === key ? { ...row, ...change } : row)),
    })

  const counts = state.selection.map((item) => item.valueIds.length).filter((count) => count > 0)
  const included = state.rows.filter((row) => !row.removed).length

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3">
        {state.selection.map((item) => {
          const attribute = byId.get(item.attributeId)
          if (!attribute) return null
          const attributeLocked = attribute.values.some((value) => locked.has(value.id))
          return (
            <fieldset
              key={item.attributeId}
              className="rounded-xl border border-border bg-surface-2/50 p-3"
            >
              <legend className="sr-only">{attribute.name}</legend>
              <div className="mb-2 flex items-center justify-between gap-2">
                <span aria-hidden="true" className="text-sm font-semibold text-text">
                  {attribute.name}
                </span>
                <button
                  type="button"
                  disabled={attributeLocked}
                  onClick={() =>
                    setSelection(state.selection.filter((s) => s.attributeId !== item.attributeId))
                  }
                  aria-label={t('matrix.removeAttribute', { name: attribute.name })}
                  title={attributeLocked ? t('matrix.lockedHint') : undefined}
                  className="grid size-8 place-items-center rounded-lg text-text-muted hover:bg-surface-2 hover:text-text focus-ring disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <X aria-hidden="true" size={16} strokeWidth={1.75} />
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {attribute.values.map((value) => {
                  const pressed = item.valueIds.includes(value.id)
                  const valueLocked = locked.has(value.id)
                  return (
                    <button
                      key={value.id}
                      type="button"
                      aria-pressed={pressed}
                      disabled={valueLocked}
                      title={valueLocked ? t('matrix.lockedHint') : undefined}
                      onClick={() => toggleValue(item.attributeId, value.id)}
                      className={cn(
                        'inline-flex h-9 items-center gap-1.5 rounded-full border px-3 text-sm font-medium',
                        'transition-colors duration-150 ease-out focus-ring',
                        pressed
                          ? 'border-primary bg-primary-soft text-primary'
                          : 'border-border bg-surface text-text hover:border-border-strong',
                        valueLocked && 'cursor-not-allowed',
                      )}
                    >
                      {valueLocked ? (
                        <Lock aria-hidden="true" size={14} strokeWidth={2} />
                      ) : (
                        pressed && <Check aria-hidden="true" size={14} strokeWidth={2.5} />
                      )}
                      {value.value}
                    </button>
                  )
                })}
              </div>
            </fieldset>
          )
        })}

        {available.length > 0 && (
          <div className="flex flex-wrap items-end gap-2">
            <Select
              label={t('matrix.addAttribute')}
              value={adding}
              onChange={(event) => setAdding(event.target.value)}
              placeholder={t('matrix.chooseAttribute')}
              options={available.map((attribute) => ({
                value: attribute.id,
                label: attribute.name,
              }))}
              wrapperClassName="min-w-0 flex-1 sm:max-w-xs"
            />
            <Button
              variant="secondary"
              disabled={!adding}
              onClick={() => {
                setSelection([...state.selection, { attributeId: adding, valueIds: [] }])
                setAdding('')
              }}
              leadingIcon={<Plus aria-hidden="true" size={18} strokeWidth={2} />}
            >
              {t('matrix.add')}
            </Button>
          </div>
        )}
        {state.selection.length === 0 && (
          <p className="text-sm text-text-muted">{t('matrix.noAttributesHint')}</p>
        )}
      </div>

      <div
        className="flex flex-wrap items-center gap-2 border-t border-border pt-4"
        aria-live="polite"
      >
        {counts.length > 1 && (
          <span className="text-sm text-text-muted tabular" aria-hidden="true">
            {counts.join(' × ')} =
          </span>
        )}
        <span className="rounded-full bg-accent-soft px-3 py-1 text-sm font-bold text-accent-ink tabular">
          {t('matrix.variantCount', { count: included })}
        </span>
      </div>

      {state.rows.length > 1 && <BulkApply state={state} onChange={onChange} />}

      {formError && (
        <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2.5 text-sm text-danger-ink">
          {t(`productForm.errors.${formError.key}` as 'productForm.errors.noVariants')}
        </p>
      )}

      <ul className="flex flex-col gap-2" aria-label={t('matrix.rowsLabel')}>
        {state.rows.map((row) => (
          <MatrixRow
            key={row.key}
            row={row}
            errors={errors[row.key]}
            onChange={(change) => updateRow(row.key, change)}
          />
        ))}
      </ul>
    </div>
  )
}

function MatrixRow({
  row,
  errors,
  onChange,
}: {
  row: VariantRow
  errors: RowErrors | undefined
  onChange: (change: Partial<VariantRow>) => void
}) {
  const { t } = useTranslation()
  const id = useId()
  const name = row.labels.join(' / ') || t('products.baseVariant')
  const message = (error: FieldError | undefined) =>
    error
      ? t(`productForm.errors.${error.key}` as 'productForm.errors.skuTaken', error.params)
      : null

  if (row.removed) {
    // Switching a saved variant off can fail too (e.g. the last active one of a product on sale).
    const removeError = message(errors?.row)
    return (
      <li
        data-row={row.key}
        className={cn(
          'flex flex-col gap-1.5 rounded-xl border border-dashed px-3 py-2 text-sm text-text-muted',
          removeError ? 'border-danger' : 'border-border',
        )}
      >
        <div className="flex items-center justify-between gap-3">
          <span className="min-w-0 truncate line-through">{name}</span>
          <span className="flex shrink-0 items-center gap-2">
            <Badge tone="muted">{row.variantId ? t('matrix.inactive') : t('matrix.skipped')}</Badge>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onChange({ removed: false })}
              aria-label={t('matrix.restore', { name })}
              leadingIcon={<RotateCcw aria-hidden="true" size={16} strokeWidth={1.75} />}
            >
              <span className="hidden sm:inline">{t('matrix.restoreShort')}</span>
            </Button>
          </span>
        </div>
        {removeError && (
          <p role="alert" className="text-danger-ink">
            {removeError}
          </p>
        )}
      </li>
    )
  }

  const skuError = message(errors?.sku)
  const priceError = message(errors?.price)
  const stockError = message(errors?.stock)
  const rowError = message(errors?.row)

  return (
    <li
      data-row={row.key}
      className={cn(
        'flex flex-col gap-2 rounded-xl border border-border bg-surface p-3',
        errors && 'border-danger',
      )}
    >
      <div className="flex min-w-0 items-center gap-2">
        <span className="min-w-0 font-semibold break-words text-text">{name}</span>
        {!row.variantId && <Badge tone="info">{t('matrix.new')}</Badge>}
        {row.reserved > 0 && (
          <Badge tone="accent" className="tabular">
            {t('matrix.reserved', { count: row.reserved })}
          </Badge>
        )}
        <button
          type="button"
          onClick={() => onChange({ removed: true })}
          aria-label={t('matrix.remove', { name })}
          className="-my-1 ml-auto grid size-9 shrink-0 place-items-center rounded-lg text-text-muted transition-colors duration-150 ease-out hover:bg-danger-soft hover:text-danger-ink focus-ring"
        >
          <Trash2 aria-hidden="true" size={18} strokeWidth={1.75} />
        </button>
      </div>
      <div className="grid grid-cols-2 items-start gap-2 sm:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_6rem]">
        <Cell
          label="SKU"
          error={skuError}
          errorId={`${id}-sku`}
          className="col-span-2 sm:col-span-1"
        >
          <input
            value={row.sku}
            onChange={(event) => onChange({ sku: event.target.value, skuAuto: false })}
            aria-label={t('matrix.skuFor', { name })}
            aria-invalid={skuError ? true : undefined}
            aria-describedby={skuError ? `${id}-sku` : undefined}
            maxLength={64}
            autoCapitalize="characters"
            spellCheck={false}
            className={inputClass}
          />
        </Cell>
        <Cell label={t('matrix.price')} error={priceError} errorId={`${id}-price`}>
          <div className="relative">
            <input
              value={row.price}
              onChange={(event) => onChange({ price: event.target.value })}
              onBlur={(event) => onChange({ price: normalizeSomInput(event.target.value) })}
              aria-label={t('matrix.priceFor', { name })}
              aria-invalid={priceError ? true : undefined}
              aria-describedby={priceError ? `${id}-price` : undefined}
              inputMode="decimal"
              placeholder="0"
              className={cn(inputClass, 'pr-12 text-right')}
            />
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-y-0 right-2.5 flex items-center text-xs text-text-muted"
            >
              so'm
            </span>
          </div>
        </Cell>
        <Cell label={t('matrix.stock')} error={stockError} errorId={`${id}-stock`}>
          <input
            value={row.stock}
            onChange={(event) => onChange({ stock: event.target.value.replace(/[^\d]/g, '') })}
            aria-label={t('matrix.stockFor', { name })}
            aria-invalid={stockError ? true : undefined}
            aria-describedby={stockError ? `${id}-stock` : undefined}
            inputMode="numeric"
            className={cn(inputClass, 'text-right')}
          />
        </Cell>
      </div>
      {rowError && (
        <p role="alert" className="text-sm text-danger-ink">
          {rowError}
        </p>
      )}
    </li>
  )
}

function Cell({
  label,
  error,
  errorId,
  className,
  children,
}: {
  label: string
  error: string | null
  errorId: string
  className?: string
  children: ReactNode
}) {
  return (
    <div className={cn('flex min-w-0 flex-col gap-1', className)}>
      <span aria-hidden="true" className="text-xs font-medium text-text-muted">
        {label}
      </span>
      {children}
      {error && (
        <p id={errorId} role="alert" className="text-xs text-danger-ink">
          {error}
        </p>
      )}
    </div>
  )
}

function BulkApply({
  state,
  onChange,
}: {
  state: MatrixState
  onChange: (s: MatrixState) => void
}) {
  const { t } = useTranslation()
  const [price, setPrice] = useState('')
  const [stock, setStock] = useState('')
  const apply = () => {
    onChange({
      ...state,
      rows: state.rows.map((row) =>
        row.removed
          ? row
          : {
              ...row,
              ...(price.trim() ? { price: normalizeSomInput(price) } : {}),
              ...(stock.trim() ? { stock: stock.trim() } : {}),
            },
      ),
    })
    setPrice('')
    setStock('')
  }
  return (
    <div className="grid grid-cols-2 items-end gap-2 rounded-xl bg-surface-2 p-3 sm:flex sm:flex-wrap">
      <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-text-muted sm:w-48">
        {t('matrix.bulkPrice')}
        <input
          value={price}
          onChange={(event) => setPrice(event.target.value)}
          inputMode="decimal"
          placeholder="so'm"
          className={cn(inputClass, 'bg-surface text-right')}
        />
      </label>
      <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-text-muted sm:w-28">
        {t('matrix.bulkStock')}
        <input
          value={stock}
          onChange={(event) => setStock(event.target.value.replace(/[^\d]/g, ''))}
          inputMode="numeric"
          className={cn(inputClass, 'bg-surface text-right')}
        />
      </label>
      <Button
        variant="secondary"
        onClick={apply}
        disabled={!price.trim() && !stock.trim()}
        className="col-span-2 sm:col-span-1"
      >
        {t('matrix.applyAll')}
      </Button>
    </div>
  )
}
