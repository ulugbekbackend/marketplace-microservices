const pad = (value: number) => String(value).padStart(2, '0')

/**
 * "27.09.2026, 17:42" in the viewer's time zone. Built by hand: browsers ship different ICU data
 * for `uz-UZ`, and dates must look the same everywhere.
 */
export function formatDateTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${date.getFullYear()}, ${pad(date.getHours())}:${pad(date.getMinutes())}`
}
