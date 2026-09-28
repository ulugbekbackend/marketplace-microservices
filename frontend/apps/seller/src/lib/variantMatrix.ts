import type { Attribute, SellerVariant } from '@bozorcha/api-client'
import { tiyinToSomInput } from './money'

/** Attribute values picked for the matrix, in the order the seller added the attribute. */
export type AttributeSelection = { attributeId: string; valueIds: string[] }

/** The server state of an existing variant, to send only what changed. */
export type VariantOriginal = { sku: string; priceTiyin: number; stock: number; active: boolean }

/** One row of the variant matrix: an attribute value combination and its editable fields. */
export type VariantRow = {
  /** Order-independent id of the combination (see `combinationKey`). */
  key: string
  valueIds: string[]
  /** Value labels for display, e.g. ["Qizil", "M"]. */
  labels: string[]
  /** Set once the variant exists on the server. */
  variantId: string | null
  sku: string
  /** The SKU is still the generated suggestion and follows title changes. */
  skuAuto: boolean
  /** So'm as typed; converted to integer tiyin only when saving. */
  price: string
  stock: string
  /** New rows: not created. Existing rows: deactivated. */
  removed: boolean
  /** Units held by open orders (existing variants only). */
  reserved: number
  original: VariantOriginal | null
}

/** Key of a combination without attribute values (a product with a single plain variant). */
export const BASE_KEY = 'base'

/** Cartesian product: `[[a, b], [1, 2]]` -> `[[a, 1], [a, 2], [b, 1], [b, 2]]`; `[]` -> `[[]]`. */
export function cartesian<T>(lists: readonly (readonly T[])[]): T[][] {
  return lists.reduce<T[][]>(
    (combos, list) => combos.flatMap((combo) => list.map((item) => [...combo, item])),
    [[]],
  )
}

/** The same values in any order give the same key, matching how the API compares variants. */
export function combinationKey(valueIds: readonly string[]): string {
  return valueIds.length ? [...valueIds].sort().join('+') : BASE_KEY
}

/** Uzbek Latin text -> SKU-safe upper case: "Qo'ng'ir rang" -> "QONGIR-RANG". */
export function skuPart(text: string): string {
  return text
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/['`ʻʼ‘’]/g, '')
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

export const SKU_MAX_LENGTH = 64
/** Same rule as the catalog API. */
export const SKU_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/

/** Short SKU prefix from the product title. */
export function skuBase(title: string): string {
  const base = skuPart(title).slice(0, 16).replace(/-+$/, '')
  return base || 'SKU'
}

/** A unique, valid SKU suggestion: base plus value parts, numbered when taken. */
export function suggestSku(base: string, labels: readonly string[], taken: ReadonlySet<string>) {
  const stem = [base, ...labels.map(skuPart)]
    .filter(Boolean)
    .join('-')
    .slice(0, SKU_MAX_LENGTH)
    .replace(/-+$/, '')
  if (!taken.has(stem)) return stem
  for (let n = 2; ; n++) {
    const suffix = `-${n}`
    const candidate = `${stem.slice(0, SKU_MAX_LENGTH - suffix.length).replace(/-+$/, '')}${suffix}`
    if (!taken.has(candidate)) return candidate
  }
}

type ValueInfo = { attributeId: string; label: string }

function valueIndex(attributes: readonly Attribute[]): Map<string, ValueInfo> {
  const index = new Map<string, ValueInfo>()
  for (const attribute of attributes) {
    for (const value of attribute.values) {
      index.set(value.id, { attributeId: attribute.id, label: value.value })
    }
  }
  return index
}

/**
 * Price a new combination starts with: that of the row sharing the most values with it (or the
 * plain row), so adding a size to a priced colour keeps the price. Stock is never copied.
 */
function inheritedPrice(valueIds: readonly string[], rows: readonly VariantRow[]): string {
  let best: VariantRow | null = null
  let bestShared = -1
  for (const row of rows) {
    if (row.removed || !row.price.trim()) continue
    const shared = row.valueIds.filter((id) => valueIds.includes(id)).length
    if ((shared > 0 || row.valueIds.length === 0) && shared > bestShared) {
      best = row
      bestShared = shared
    }
  }
  return best?.price ?? ''
}

function newRow(valueIds: string[], labels: string[], sku: string, price: string): VariantRow {
  return {
    key: combinationKey(valueIds),
    valueIds,
    labels,
    variantId: null,
    sku,
    skuAuto: true,
    price,
    stock: '0',
    removed: false,
    reserved: 0,
    original: null,
  }
}

/**
 * Rows for the current selection: every combination of the picked values, keeping rows the
 * seller already edited, plus existing variants that fall outside the selection (they are
 * never dropped, only deactivated). An attribute without picked values is ignored.
 */
export function syncRows(
  rows: readonly VariantRow[],
  selection: readonly AttributeSelection[],
  attributes: readonly Attribute[],
  base: string,
): VariantRow[] {
  const values = valueIndex(attributes)
  const lists = selection.filter((item) => item.valueIds.length > 0).map((item) => item.valueIds)
  const byKey = new Map(rows.map((row) => [row.key, row]))
  const taken = new Set(rows.map((row) => row.sku))
  const result: VariantRow[] = []
  const seen = new Set<string>()

  for (const combo of cartesian(lists)) {
    const key = combinationKey(combo)
    seen.add(key)
    const existing = byKey.get(key)
    if (existing) {
      result.push(existing)
      continue
    }
    const labels = combo.map((id) => values.get(id)?.label ?? id)
    const sku = suggestSku(base, labels, taken)
    taken.add(sku)
    result.push(newRow(combo, labels, sku, inheritedPrice(combo, rows)))
  }
  for (const row of rows) {
    if (row.variantId && !seen.has(row.key)) result.push(row)
  }
  return result
}

/** Regenerates SKUs the seller has not typed over (e.g. after the title changed). */
export function refreshAutoSkus(rows: readonly VariantRow[], base: string): VariantRow[] {
  const taken = new Set(rows.filter((row) => !row.skuAuto || row.variantId).map((row) => row.sku))
  return rows.map((row) => {
    if (!row.skuAuto || row.variantId) return row
    const sku = suggestSku(base, row.labels, taken)
    taken.add(sku)
    return sku === row.sku ? row : { ...row, sku }
  })
}

/** Existing variants as rows; inactive ones start as removed. */
export function rowsFromVariants(variants: readonly SellerVariant[]): VariantRow[] {
  return variants.map((variant) => {
    const valueIds = variant.attributes.map((attribute) => attribute.value_id)
    const stock = variant.stock ?? 0
    const active = variant.is_active ?? true
    return {
      key: combinationKey(valueIds),
      valueIds,
      labels: variant.attributes.map((attribute) => attribute.value),
      variantId: variant.id,
      sku: variant.sku,
      skuAuto: false,
      price: tiyinToSomInput(variant.price_tiyin),
      stock: String(stock),
      removed: !active,
      reserved: variant.reserved ?? 0,
      original: { sku: variant.sku, priceTiyin: variant.price_tiyin, stock, active },
    }
  })
}

/** The attributes and values existing variants use, in order of first appearance. */
export function selectionFromVariants(
  variants: readonly SellerVariant[],
  attributes: readonly Attribute[],
): AttributeSelection[] {
  const values = valueIndex(attributes)
  const selection: AttributeSelection[] = []
  for (const variant of variants) {
    for (const { value_id } of variant.attributes) {
      const attributeId = values.get(value_id)?.attributeId
      if (!attributeId) continue
      let item = selection.find((entry) => entry.attributeId === attributeId)
      if (!item) {
        item = { attributeId, valueIds: [] }
        selection.push(item)
      }
      if (!item.valueIds.includes(value_id)) item.valueIds.push(value_id)
    }
  }
  return selection
}

/**
 * Matrix state for an existing product. Combinations the product never had start as removed,
 * so opening the editor never proposes variants the seller did not ask for.
 */
export function initialMatrix(
  variants: readonly SellerVariant[],
  attributes: readonly Attribute[],
  base: string,
): { selection: AttributeSelection[]; rows: VariantRow[] } {
  const selection = selectionFromVariants(variants, attributes)
  const existing = rowsFromVariants(variants)
  if (existing.length === 0) return { selection, rows: [] }
  const rows = syncRows(existing, selection, attributes, base).map((row) =>
    row.variantId ? row : { ...row, removed: true },
  )
  return { selection, rows }
}

/** Value ids used by saved variants: they cannot be unpicked, only their variants deactivated. */
export function lockedValueIds(rows: readonly VariantRow[]): Set<string> {
  return new Set(rows.filter((row) => row.variantId).flatMap((row) => row.valueIds))
}
