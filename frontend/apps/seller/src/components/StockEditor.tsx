import { queryKeys, useUpdateVariantStock, type SellerVariant } from '@bozorcha/api-client'
import { Button, cn, useToast } from '@bozorcha/ui'
import { useQueryClient } from '@tanstack/react-query'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { STOCK_MAX } from '../lib/productForm'
import { reservedFromError } from '../lib/saveProduct'

type StockEditorProps = {
  productId: string
  variant: SellerVariant
  /** Accessible name of the variant, e.g. "Qizil / M". */
  variantName: string
}

type StockError = { key: 'invalid' } | { key: 'belowReserved'; count: number } | { key: 'failed' }

/**
 * Inline stock field: Enter or the save button sends it, Escape restores the saved value. The
 * table updates at once and rolls back if the server refuses (e.g. orders hold more units).
 */
export function StockEditor({ productId, variant, variantName }: StockEditorProps) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const update = useUpdateVariantStock()
  const saved = variant.stock ?? 0
  const [draft, setDraft] = useState<string | null>(null)
  const [error, setError] = useState<StockError | null>(null)
  const errorId = useId()
  const value = draft ?? String(saved)
  const dirty = draft !== null && draft !== String(saved)

  const reset = () => {
    setDraft(null)
    setError(null)
  }

  const submit = () => {
    if (!dirty || update.isPending) return
    const trimmed = value.trim()
    if (!/^\d+$/.test(trimmed) || Number(trimmed) > STOCK_MAX) {
      setError({ key: 'invalid' })
      return
    }
    const stock = Number(trimmed)
    const reserved = variant.reserved ?? 0
    if (stock < reserved) {
      setError({ key: 'belowReserved', count: reserved })
      return
    }
    setError(null)
    update.mutate(
      { productId, variantId: variant.id, stock },
      {
        onSuccess: () => {
          setDraft(null)
          toast({ title: t('stock.saved', { name: variantName }), tone: 'success' })
        },
        onError: (failure) => {
          const count = reservedFromError(failure)
          setError(count === null ? { key: 'failed' } : { key: 'belowReserved', count })
          // Reserved units changed on the server: show the current numbers.
          void queryClient.invalidateQueries({ queryKey: queryKeys.sellerProduct(productId) })
        },
      },
    )
  }

  const message =
    error?.key === 'belowReserved'
      ? t('stock.belowReserved', { count: error.count })
      : error?.key === 'invalid'
        ? t('stock.invalid', { max: STOCK_MAX })
        : error?.key === 'failed'
          ? t('stock.failed')
          : null

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-1.5">
        <input
          type="text"
          inputMode="numeric"
          value={value}
          aria-label={t('stock.label', { name: variantName })}
          aria-invalid={error ? true : undefined}
          aria-describedby={message ? errorId : undefined}
          onChange={(event) => {
            setError(null)
            setDraft(event.target.value.replace(/[^\d]/g, ''))
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              submit()
            } else if (event.key === 'Escape' && dirty) {
              event.preventDefault()
              reset()
            }
          }}
          className={cn(
            'h-9 w-20 rounded-lg border border-border bg-surface px-2 text-right text-sm text-text tabular',
            'transition-colors duration-150 ease-out hover:border-border-strong',
            'focus-visible:border-primary focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-primary',
            error && 'border-danger',
          )}
        />
        {dirty && (
          <Button
            size="sm"
            onClick={submit}
            loading={update.isPending}
            aria-label={t('stock.save', { name: variantName })}
          >
            {t('common.save')}
          </Button>
        )}
      </div>
      {message && (
        <p id={errorId} role="alert" className="max-w-56 text-right text-xs text-danger-ink">
          {message}
        </p>
      )}
    </div>
  )
}
