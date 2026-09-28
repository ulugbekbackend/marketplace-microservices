import type { SellerVariant } from '@bozorcha/api-client'

/** "Qizil / M" from a variant's attribute values, or the fallback for a plain variant. */
export function variantName(variant: SellerVariant, fallback: string): string {
  return variant.attributes.map((attribute) => attribute.value).join(' / ') || fallback
}
