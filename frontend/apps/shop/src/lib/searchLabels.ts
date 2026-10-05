import type { PriceRangeFacet } from '@bozorcha/api-client'
import { formatPrice } from '@bozorcha/ui'
import type { TFunction } from 'i18next'

const KNOWN_ATTRIBUTES = ['color', 'size', 'shoe_size', 'memory', 'weight'] as const

const upperFirst = (text: string) => text.charAt(0).toLocaleUpperCase('uz') + text.slice(1)

/** Display name of an attribute code; unknown codes are humanised (`shoe_size` -> "Shoe size"). */
export function attributeLabel(t: TFunction, code: string): string {
  const known = KNOWN_ATTRIBUTES.find((c) => c === code)
  return known ? t(`catalog.attributes.${known}`) : upperFirst(code.replaceAll('_', ' '))
}

/** Attribute values are stored lowercase ("qizil"); show them as labels ("Qizil"). */
export const valueLabel = (value: string) => upperFirst(value)

/** The number part of a price, without the currency: `10000000` -> `100 000`. */
const amount = (tiyin: number) => formatPrice(tiyin).replace(/\s?so'm$/, '')

/** "100 000 so'mgacha", "100 000 – 500 000 so'm", "5 000 000 so'mdan". */
export function priceBucketLabel(t: TFunction, bucket: PriceRangeFacet): string {
  const { from_tiyin: from, to_tiyin: to } = bucket
  if (from === null && to === null) return t('catalog.anyPrice')
  if (from === null) return t('catalog.priceUpTo', { price: formatPrice(to!) })
  if (to === null) return t('catalog.priceFrom', { price: formatPrice(from) })
  return t('catalog.priceBetween', { from: amount(from), to: formatPrice(to) })
}

/** A price filter from the URL (both bounds inclusive) as text. */
export function priceRangeLabel(t: TFunction, min: number | null, max: number | null): string {
  // Bucket filters end one tiyin below a round bound: show the round number.
  const upper = max === null ? null : (max + 1) % 100 === 0 ? max + 1 : max
  return priceBucketLabel(t, { key: 'custom', from_tiyin: min, to_tiyin: upper, count: 0 })
}
