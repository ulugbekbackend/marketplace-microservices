/** Payouts listed per page. */
export const PAYOUTS_PAGE_SIZE = 20

const pad = (value: number) => String(value).padStart(2, '0')

/** "28.09.2026": a calendar date (`YYYY-MM-DD`), with no time zone shift. */
export function formatDay(day: string): string {
  const [year, month, date] = day.split('-')
  return year && month && date ? `${date}.${month}.${year}` : day
}

/**
 * The week a payout covers. `period_end` is the next Monday (exclusive), so the last day shown
 * is the Sunday before it.
 */
export function payoutWeek(periodStart: string, periodEnd: string): { from: string; to: string } {
  const end = new Date(`${periodEnd}T00:00:00Z`)
  end.setUTCDate(end.getUTCDate() - 1)
  const last = `${end.getUTCFullYear()}-${pad(end.getUTCMonth() + 1)}-${pad(end.getUTCDate())}`
  return { from: formatDay(periodStart), to: formatDay(last) }
}

/** Page number from `?page=`, at least 1. */
export function readPage(params: URLSearchParams): number {
  const page = Number(params.get('page'))
  return Number.isInteger(page) && page > 1 ? page : 1
}

/** The same week in few characters for narrow screens: "21–27.09.2026", "31.08–06.09.2026". */
export function payoutWeekShort(periodStart: string, periodEnd: string): string {
  const { from, to } = payoutWeek(periodStart, periodEnd)
  const [fromDay, fromMonth, fromYear] = from.split('.')
  const [, toMonth, toYear] = to.split('.')
  if (fromYear !== toYear) return `${from}–${to}`
  if (fromMonth !== toMonth) return `${fromDay}.${fromMonth}–${to}`
  return `${fromDay}–${to}`
}
