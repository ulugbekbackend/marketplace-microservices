import {
  CLIENT_ERROR,
  errorDetail,
  isApiError,
  type sellerCatalogEndpoints,
  type ProductUpdateRequest,
  type SellerProductDetail,
  type SellerVariant,
  type VariantUpdateRequest,
} from '@bozorcha/api-client'
import { somToTiyin } from './money'
import type { FieldError, ProductValues, RowErrors } from './productForm'
import type { VariantRow } from './variantMatrix'

type SellerApi = ReturnType<typeof sellerCatalogEndpoints>

export type SaveInput = {
  productId: string | null
  values: ProductValues
  /** Last known server state of the product; null when creating. */
  baseline: SellerProductDetail | null
  rows: readonly VariantRow[]
}

export type SaveResult = {
  product: SellerProductDetail
  /** Rows with server ids and baselines updated for what was saved. */
  rows: VariantRow[]
  /** Per-row failures, keyed by row key. Empty when everything was saved. */
  failures: Record<string, RowErrors>
}

/** Maps a variant request failure to the field it concerns. */
export function variantFailure(error: unknown): RowErrors {
  if (!isApiError(error)) return { row: { key: 'unknown' } }
  switch (error.code) {
    case 'SKU_TAKEN':
      return { sku: { key: 'skuTaken' } }
    case 'STOCK_BELOW_RESERVED': {
      const reserved = errorDetail(error, 'reserved')
      return {
        stock: {
          key: 'stockBelowReserved',
          params: { count: typeof reserved === 'number' ? reserved : 0 },
        },
      }
    }
    case 'VARIANT_EXISTS':
      return { row: { key: 'variantExists' } }
    case CLIENT_ERROR.NETWORK:
      return { row: { key: 'network' } }
    default:
      return { row: { key: 'unknown' } }
  }
}

/** Reserved units from a 409 `STOCK_BELOW_RESERVED`, or null for other errors. */
export function reservedFromError(error: unknown): number | null {
  if (!isApiError(error) || error.code !== 'STOCK_BELOW_RESERVED') return null
  const reserved = errorDetail(error, 'reserved')
  return typeof reserved === 'number' ? reserved : null
}

function productChanges(values: ProductValues, baseline: SellerProductDetail) {
  const changes: ProductUpdateRequest = {}
  if (values.title.trim() !== baseline.title) changes.title = values.title.trim()
  if (values.description !== (baseline.description ?? '')) changes.description = values.description
  if (values.category_id !== baseline.category.id) changes.category_id = values.category_id
  if (values.status !== baseline.status) changes.status = values.status
  return changes
}

const savedRow = (row: VariantRow, variant: SellerVariant): VariantRow => ({
  ...row,
  variantId: variant.id,
  sku: variant.sku,
  skuAuto: false,
  reserved: variant.reserved ?? 0,
  original: {
    sku: variant.sku,
    priceTiyin: variant.price_tiyin,
    stock: variant.stock ?? 0,
    active: variant.is_active ?? true,
  },
})

/**
 * Saves the product, then each variant in turn: new combinations are created, existing ones
 * get only the fields that changed (price and SKU, active flag, stock separately). A failing
 * variant does not stop the others; its error is returned for the row. Product errors throw.
 * Prices are validated beforehand, so every price here converts to integer tiyin.
 */
export async function saveProduct(api: SellerApi, input: SaveInput): Promise<SaveResult> {
  const { values } = input
  let productId = input.productId
  if (!productId) {
    const created = await api.createProduct({
      title: values.title.trim(),
      description: values.description,
      category_id: values.category_id,
      status: values.status === 'archived' ? 'draft' : values.status,
    })
    productId = created.id
  } else if (input.baseline) {
    const changes = productChanges(values, input.baseline)
    if (Object.keys(changes).length) await api.updateProduct(productId, changes)
  }

  const rows: VariantRow[] = []
  const failures: Record<string, RowErrors> = {}
  const fail = (row: VariantRow, error: unknown) => {
    failures[row.key] = variantFailure(error)
    rows.push(row)
  }

  for (const row of input.rows) {
    const priceTiyin = somToTiyin(row.price)
    const stock = Number(row.stock)
    if (!row.variantId || !row.original) {
      if (row.removed) {
        rows.push(row)
        continue
      }
      try {
        const variant = await api.createVariant(productId, {
          sku: row.sku.trim(),
          price_tiyin: priceTiyin!,
          stock,
          attribute_value_ids: row.valueIds,
        })
        rows.push(savedRow(row, variant))
      } catch (error) {
        fail(row, error)
      }
      continue
    }

    const { original } = row
    let current = row
    try {
      const patch: VariantUpdateRequest = {}
      if (!row.removed) {
        if (row.sku.trim() !== original.sku) patch.sku = row.sku.trim()
        if (priceTiyin !== null && priceTiyin !== original.priceTiyin)
          patch.price_tiyin = priceTiyin
      }
      if (!row.removed !== original.active) patch.is_active = !row.removed
      if (Object.keys(patch).length) {
        current = savedRow(row, await api.updateVariant(row.variantId, patch))
      }
      if (!row.removed && stock !== original.stock) {
        current = savedRow(row, await api.setStock(row.variantId, { stock }))
      }
      rows.push(current)
    } catch (error) {
      failures[row.key] = variantFailure(error)
      // What did get saved (e.g. the price) becomes the baseline; the failed part stays dirty.
      rows.push(current)
    }
  }

  const product = await api.product(productId)
  return { product, rows, failures }
}

/** i18n key under `productForm.errors` for a product request that failed. */
export function productSaveError(error: unknown): FieldError {
  if (!isApiError(error)) return { key: 'unknown' }
  if (error.code === CLIENT_ERROR.NETWORK) return { key: 'network' }
  if (error.code === 'SELLER_NOT_FOUND') return { key: 'shopNotReady' }
  if (error.code === 'VALIDATION_ERROR' || error.status === 400) return { key: 'rejected' }
  return { key: 'unknown' }
}
