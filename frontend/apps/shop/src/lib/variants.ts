import type { ProductVariant } from '@bozorcha/api-client'

/** Selected value per attribute code, e.g. `{ color: 'Qora', size: 'M' }`. */
export type Selection = Record<string, string>

/**
 * - `available`: an in-stock variant matches this value together with the other selections.
 * - `incompatible`: in stock, but only with different values for the other attributes;
 *   choosing it switches those.
 * - `unavailable`: no in-stock variant has this value at all (disabled).
 */
export type OptionState = 'available' | 'incompatible' | 'unavailable'

export type AttributeGroup = {
  code: string
  name: string
  values: string[]
}

/** A variant can be bought when the API marks it in stock and units remain unreserved. */
export const isBuyable = (variant: ProductVariant) => variant.in_stock && variant.available > 0

const valueOf = (variant: ProductVariant, code: string) =>
  variant.attributes.find((attribute) => attribute.code === code)?.value

/** Attribute groups in first-seen order, values in first-seen order. */
export function attributeGroups(variants: ProductVariant[]): AttributeGroup[] {
  const groups = new Map<string, AttributeGroup>()
  for (const variant of variants) {
    for (const { code, name, value } of variant.attributes) {
      let group = groups.get(code)
      if (!group) {
        group = { code, name, values: [] }
        groups.set(code, group)
      }
      if (!group.values.includes(value)) group.values.push(value)
    }
  }
  return [...groups.values()]
}

const matches = (variant: ProductVariant, selection: Selection, skip?: string) =>
  Object.entries(selection).every(
    ([code, value]) => code === skip || valueOf(variant, code) === value,
  )

/** The variant for a complete selection, or undefined if that combination does not exist. */
export function findVariant(
  variants: ProductVariant[],
  selection: Selection,
): ProductVariant | undefined {
  const codes = attributeGroups(variants).map((group) => group.code)
  if (variants.length === 1 && codes.length === 0) return variants[0]
  if (!codes.every((code) => selection[code] !== undefined)) return undefined
  return variants.find((variant) => matches(variant, selection))
}

/** Starts on the cheapest in-stock variant (falls back to the first one). */
export function initialSelection(variants: ProductVariant[]): Selection {
  const inStock = variants.filter(isBuyable)
  const pool = inStock.length > 0 ? inStock : variants
  const start = [...pool].sort((a, b) => a.price_tiyin - b.price_tiyin)[0]
  return Object.fromEntries(start?.attributes.map(({ code, value }) => [code, value]) ?? [])
}

export function optionState(
  variants: ProductVariant[],
  selection: Selection,
  code: string,
  value: string,
): OptionState {
  const withValue = variants.filter(
    (variant) => isBuyable(variant) && valueOf(variant, code) === value,
  )
  if (withValue.length === 0) return 'unavailable'
  return withValue.some((variant) => matches(variant, selection, code))
    ? 'available'
    : 'incompatible'
}

/**
 * Applies a choice. If the resulting combination is not in stock, moves the other attributes
 * to the closest in-stock variant that has the chosen value (keeping as many choices as possible).
 */
export function selectOption(
  variants: ProductVariant[],
  selection: Selection,
  code: string,
  value: string,
): Selection {
  const next = { ...selection, [code]: value }
  const exact = findVariant(variants, next)
  if (exact && isBuyable(exact)) return next

  const candidates = variants.filter((variant) => valueOf(variant, code) === value)
  if (candidates.length === 0) return next
  const score = (variant: ProductVariant) =>
    (isBuyable(variant) ? 1000 : 0) +
    Object.entries(selection).filter(([c, v]) => c !== code && valueOf(variant, c) === v).length
  const best = [...candidates].sort((a, b) => score(b) - score(a))[0]!
  return Object.fromEntries(best.attributes.map((attribute) => [attribute.code, attribute.value]))
}
