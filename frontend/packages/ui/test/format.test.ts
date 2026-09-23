import { describe, expect, it, vi } from 'vitest'
import { discountPercent, formatPrice } from '../src/lib/format'

const NBSP = String.fromCharCode(0xa0)
const plain = (text: string) => text.replaceAll(NBSP, ' ')

describe('formatPrice', () => {
  it("formats tiyin as grouped so'm", () => {
    expect(plain(formatPrice(125_000_000))).toBe("1 250 000 so'm")
  })

  it('uses non-breaking spaces so prices never wrap', () => {
    expect(formatPrice(125_000_000)).toBe(['1', '250', '000', "so'm"].join(NBSP))
  })

  it('handles small, zero and fractional amounts', () => {
    expect(plain(formatPrice(99_900))).toBe("999 so'm")
    expect(plain(formatPrice(0))).toBe("0 so'm")
    expect(plain(formatPrice(150_050))).toBe("1 500,5 so'm")
  })

  it('is independent of the engine ICU data (Chromium falls back to 1,250,000)', () => {
    const english = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })
    const original = Intl.NumberFormat.prototype.formatToParts
    const spy = vi
      .spyOn(Intl.NumberFormat.prototype, 'formatToParts')
      .mockImplementation((value) => original.call(english, value as number))
    try {
      expect(plain(formatPrice(125_000_050))).toBe("1 250 000,5 so'm")
    } finally {
      spy.mockRestore()
    }
  })

  it('rejects non-finite input', () => {
    expect(() => formatPrice(Number.NaN)).toThrow(RangeError)
  })
})

describe('discountPercent', () => {
  it('rounds the discount to a whole percent', () => {
    expect(discountPercent(75_000, 100_000)).toBe(25)
    expect(discountPercent(66_600, 100_000)).toBe(33)
  })

  it('returns null without a higher old price', () => {
    expect(discountPercent(100, null)).toBeNull()
    expect(discountPercent(100, 100)).toBeNull()
    expect(discountPercent(100, 50)).toBeNull()
  })
})
