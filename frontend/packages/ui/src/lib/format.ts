const TIYIN_PER_SOM = 100
const NBSP = String.fromCharCode(0xa0)

const somFormatter = new Intl.NumberFormat('uz-UZ', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
})

/**
 * Format an integer amount of tiyin as so'm: `125000000` -> `1 250 000 so'm`.
 * Group separators and the gap before the currency are non-breaking spaces so a price never
 * wraps across lines.
 *
 * Separators are normalised from `formatToParts`: browsers ship different ICU data for `uz-UZ`
 * (Chromium's bundled data falls back to `1,250,000`), and prices must look the same everywhere.
 */
export function formatPrice(tiyin: number): string {
  if (!Number.isFinite(tiyin)) {
    throw new RangeError(`formatPrice expects a finite number, got ${tiyin}`)
  }
  const number = somFormatter
    .formatToParts(tiyin / TIYIN_PER_SOM)
    .map((part) => (part.type === 'group' ? NBSP : part.type === 'decimal' ? ',' : part.value))
    .join('')
  return `${number}${NBSP}so'm`
}

/** Whole-number percentage discount between an old and a current price, or null if none. */
export function discountPercent(priceTiyin: number, oldPriceTiyin?: number | null): number | null {
  if (!oldPriceTiyin || oldPriceTiyin <= 0 || oldPriceTiyin <= priceTiyin) return null
  return Math.round(((oldPriceTiyin - priceTiyin) / oldPriceTiyin) * 100)
}
