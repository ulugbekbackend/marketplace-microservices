/** Integer tiyin in one so'm. */
export const TIYIN_PER_SOM = 100

/** Largest accepted price: 100 billion so'm, far below Number.MAX_SAFE_INTEGER in tiyin. */
export const MAX_PRICE_TIYIN = 100_000_000_000 * TIYIN_PER_SOM

const SOM_PATTERN = /^(\d+)(?:[.,](\d{1,2}))?$/

/**
 * Parses what a seller types in a so'm field into integer tiyin, without floating point:
 * `"1 250 000"` -> `125000000`, `"12 500,5"` -> `1250050`. Spaces (also non-breaking) are group
 * separators; `,` or `.` starts at most two decimals. Returns null for anything else.
 */
export function somToTiyin(input: string): number | null {
  const compact = input.replace(/\s/g, '')
  const match = SOM_PATTERN.exec(compact)
  if (!match) return null
  const whole = match[1]!.replace(/^0+(?=\d)/, '')
  // Longer than the limit's digits cannot be a valid price; also keeps Number() exact.
  if (whole.length > 12) return null
  const fraction = (match[2] ?? '').padEnd(2, '0')
  const tiyin = Number(whole) * TIYIN_PER_SOM + Number(fraction)
  return Number.isSafeInteger(tiyin) ? tiyin : null
}

/** Integer tiyin -> editable so'm text: `125000000` -> `"1 250 000"`, `1250050` -> `"12 500,50"`. */
export function tiyinToSomInput(tiyin: number): string {
  if (!Number.isSafeInteger(tiyin) || tiyin < 0) return ''
  const whole = Math.floor(tiyin / TIYIN_PER_SOM)
  const fraction = tiyin % TIYIN_PER_SOM
  const grouped = String(whole).replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
  return fraction ? `${grouped},${String(fraction).padStart(2, '0')}` : grouped
}

/** Reformats typed so'm text with group spaces, leaving unparsable input untouched. */
export function normalizeSomInput(input: string): string {
  const tiyin = somToTiyin(input)
  return tiyin === null ? input : tiyinToSomInput(tiyin)
}
