import type { ProductStatus } from '@bozorcha/api-client'
import { z } from 'zod'
import { MAX_PRICE_TIYIN, somToTiyin } from './money'
import { SKU_PATTERN, type VariantRow } from './variantMatrix'

export const PRODUCT_STATUSES = ['draft', 'active', 'archived'] as const satisfies ProductStatus[]

export const TITLE_MAX = 200
export const DESCRIPTION_MAX = 5000
export const STOCK_MAX = 1_000_000

/** Messages are i18n keys under `productForm.errors`. */
export const productSchema = z.object({
  title: z.string().trim().min(1, 'titleRequired').max(TITLE_MAX, 'titleTooLong'),
  category_id: z.string().min(1, 'categoryRequired'),
  description: z.string().max(DESCRIPTION_MAX, 'descriptionTooLong'),
  status: z.enum(PRODUCT_STATUSES),
})

export type ProductValues = z.infer<typeof productSchema>

export type RowField = 'sku' | 'price' | 'stock' | 'row'
/** An i18n key under `productForm.errors` and its interpolation values. */
export type FieldError = { key: string; params?: Record<string, string | number> }
export type RowErrors = Partial<Record<RowField, FieldError>>

export type MatrixValidation = {
  rows: Record<string, RowErrors>
  /** Problem with the matrix as a whole. */
  form: FieldError | null
}

/** Rows that will exist after saving (not removed). */
export const includedRows = (rows: readonly VariantRow[]) => rows.filter((row) => !row.removed)

function priceError(price: string): FieldError | undefined {
  if (!price.trim()) return { key: 'priceRequired' }
  const tiyin = somToTiyin(price)
  if (tiyin === null || tiyin < 1) return { key: 'priceInvalid' }
  if (tiyin > MAX_PRICE_TIYIN) return { key: 'priceTooHigh' }
  return undefined
}

function stockError(row: VariantRow): FieldError | undefined {
  if (!/^\d+$/.test(row.stock.trim())) return { key: 'stockInvalid' }
  const stock = Number(row.stock)
  if (stock > STOCK_MAX) return { key: 'stockTooHigh', params: { max: STOCK_MAX } }
  if (stock < row.reserved) return { key: 'stockBelowReserved', params: { count: row.reserved } }
  return undefined
}

/**
 * Checks the variant rows the way the API will: SKU format and uniqueness, a positive price in
 * whole tiyin, non-negative stock not below what orders hold. An active product needs at least
 * one variant, otherwise it would be listed without a price.
 */
export function validateMatrix(
  rows: readonly VariantRow[],
  status: ProductStatus,
): MatrixValidation {
  const result: MatrixValidation = { rows: {}, form: null }
  const included = includedRows(rows)
  const skuCount = new Map<string, number>()
  for (const row of included) skuCount.set(row.sku.trim(), (skuCount.get(row.sku.trim()) ?? 0) + 1)

  for (const row of included) {
    const errors: RowErrors = {}
    const sku = row.sku.trim()
    if (!sku) errors.sku = { key: 'skuRequired' }
    else if (!SKU_PATTERN.test(sku)) errors.sku = { key: 'skuInvalid' }
    else if ((skuCount.get(sku) ?? 0) > 1) errors.sku = { key: 'skuDuplicate' }
    const price = priceError(row.price)
    if (price) errors.price = price
    const stock = stockError(row)
    if (stock) errors.stock = stock
    if (Object.keys(errors).length) result.rows[row.key] = errors
  }
  if (status === 'active' && included.length === 0) result.form = { key: 'noVariants' }
  return result
}

export const hasMatrixErrors = (validation: MatrixValidation) =>
  validation.form !== null || Object.keys(validation.rows).length > 0
