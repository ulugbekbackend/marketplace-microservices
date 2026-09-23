import type { ProductVariant } from '@bozorcha/api-client'
import { describe, expect, it } from 'vitest'
import {
  attributeGroups,
  findVariant,
  initialSelection,
  optionState,
  selectOption,
} from './variants'

const v = (
  id: string,
  color: string,
  size: string,
  price: number,
  available: number,
): ProductVariant => ({
  id,
  sku: `SKU-${id}`,
  price_tiyin: price,
  available,
  in_stock: available > 0,
  attributes: [
    { code: 'color', name: 'Rang', value: color, value_id: `color-${color}` },
    { code: 'size', name: "O'lcham", value: size, value_id: `size-${size}` },
  ],
})

// Qora: S, M (M sold out) | Oq: M, L | Yashil: S (sold out) -> Yashil is unavailable entirely
const variants = [
  v('1', 'Qora', 'S', 150_000_00, 3),
  v('2', 'Qora', 'M', 150_000_00, 0),
  v('3', 'Oq', 'M', 160_000_00, 10),
  v('4', 'Oq', 'L', 120_000_00, 2),
  v('5', 'Yashil', 'S', 150_000_00, 0),
]

describe('variant selection', () => {
  it('collects attribute groups in first-seen order', () => {
    expect(attributeGroups(variants)).toEqual([
      { code: 'color', name: 'Rang', values: ['Qora', 'Oq', 'Yashil'] },
      { code: 'size', name: "O'lcham", values: ['S', 'M', 'L'] },
    ])
  })

  it('starts on the cheapest in-stock variant', () => {
    expect(initialSelection(variants)).toEqual({ color: 'Oq', size: 'L' })
    expect(initialSelection([v('x', 'Qora', 'S', 1, 0), v('y', 'Oq', 'S', 2, 0)])).toEqual({
      color: 'Qora',
      size: 'S',
    })
  })

  it('finds the variant for a complete selection only', () => {
    expect(findVariant(variants, { color: 'Oq', size: 'M' })?.id).toBe('3')
    expect(findVariant(variants, { color: 'Oq' })).toBeUndefined()
    expect(findVariant(variants, { color: 'Oq', size: 'S' })).toBeUndefined()
  })

  it('classifies options against the other selections', () => {
    const selection = { color: 'Qora', size: 'S' }
    expect(optionState(variants, selection, 'size', 'S')).toBe('available')
    // Qora/M exists but is sold out, Oq/M is in stock -> reachable by switching colour
    expect(optionState(variants, selection, 'size', 'M')).toBe('incompatible')
    expect(optionState(variants, selection, 'size', 'L')).toBe('incompatible')
    expect(optionState(variants, selection, 'color', 'Oq')).toBe('incompatible')
    // no in-stock variant is green at all
    expect(optionState(variants, selection, 'color', 'Yashil')).toBe('unavailable')
  })

  it('keeps the other choices when the new combination is in stock', () => {
    expect(selectOption(variants, { color: 'Oq', size: 'L' }, 'size', 'M')).toEqual({
      color: 'Oq',
      size: 'M',
    })
  })

  it('moves other attributes to the closest in-stock variant', () => {
    // Qora/L does not exist -> keep L, switch colour to Oq
    expect(selectOption(variants, { color: 'Qora', size: 'S' }, 'size', 'L')).toEqual({
      color: 'Oq',
      size: 'L',
    })
    // Qora/M is sold out -> prefer in-stock Oq/M over staying on Qora
    expect(selectOption(variants, { color: 'Qora', size: 'S' }, 'size', 'M')).toEqual({
      color: 'Oq',
      size: 'M',
    })
  })

  it('handles single-variant products without attributes', () => {
    const only: ProductVariant = { ...v('9', 'x', 'y', 5, 1), attributes: [] }
    expect(attributeGroups([only])).toEqual([])
    expect(findVariant([only], initialSelection([only]))?.id).toBe('9')
  })
})
