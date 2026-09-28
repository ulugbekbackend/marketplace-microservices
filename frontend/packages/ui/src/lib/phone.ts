export const UZ_COUNTRY_CODE = '+998'
export const UZ_NATIONAL_LENGTH = 9

/** Keeps only the 9 national digits, dropping a pasted +998 / 998 prefix. */
export function nationalDigits(input: string): string {
  let digits = input.replace(/\D/g, '')
  if (digits.length > UZ_NATIONAL_LENGTH && digits.startsWith('998')) digits = digits.slice(3)
  return digits.slice(0, UZ_NATIONAL_LENGTH)
}

/** `901234567` -> `90 123 45 67` (partial input is formatted as far as it goes). */
export function formatNational(input: string): string {
  const d = nationalDigits(input)
  return [d.slice(0, 2), d.slice(2, 5), d.slice(5, 7), d.slice(7, 9)].filter(Boolean).join(' ')
}

/** `90 123 45 67` -> `+998901234567` (E.164, the format the API expects). */
export function toE164(input: string): string {
  return `${UZ_COUNTRY_CODE}${nationalDigits(input)}`
}

/** `+998901234567` -> `+998 90 123 45 67` for display. */
export function formatE164(phone: string): string {
  return `${UZ_COUNTRY_CODE} ${formatNational(phone)}`
}
