import type { SellerDailyStats, SellerStats, SubOrderStatusCounts } from '@bozorcha/api-client'
import { TIYIN_PER_SOM } from './money'

export type ChartPoint = {
  /** `YYYY-MM-DD`, a Tashkent calendar day. */
  date: string
  /** "27.09" for the axis. */
  label: string
  orders: number
  gross: number
  net: number
}

/** "2026-09-27" -> "27.09". The date is a calendar day already: no time zone conversion. */
export function dayLabel(date: string): string {
  const [, month, day] = date.split('-')
  return month && day ? `${day}.${month}` : date
}

/** "2026-09-27" -> "27.09.2026". */
export function dayLabelLong(date: string): string {
  const [year, month, day] = date.split('-')
  return year && month && day ? `${day}.${month}.${year}` : date
}

/** Daily stats as chart rows, oldest first; money stays in integer tiyin. */
export function toChartPoints(daily: readonly SellerDailyStats[]): ChartPoint[] {
  return [...daily]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((day) => ({
      date: day.date,
      label: dayLabel(day.date),
      orders: day.orders,
      gross: day.gross_tiyin,
      net: day.net_tiyin,
    }))
}

export type DailySummary = {
  orders: number
  gross: number
  net: number
  /** The day with the highest gross, null when nothing sold. */
  best: ChartPoint | null
}

export function summarize(points: readonly ChartPoint[]): DailySummary {
  let best: ChartPoint | null = null
  let orders = 0
  let gross = 0
  let net = 0
  for (const point of points) {
    orders += point.orders
    gross += point.gross
    net += point.net
    if (point.gross > 0 && (!best || point.gross > best.gross)) best = point
  }
  return { orders, gross, net, best }
}

/** A seller who never had an order: every count is zero. */
export function hasNoOrders(stats: SellerStats): boolean {
  return Object.values(stats.by_status).every((count) => count === 0)
}

export const totalCount = (counts: SubOrderStatusCounts) =>
  Object.values(counts).reduce((sum, count) => sum + count, 0)

const trim = (value: number) => {
  const rounded = value >= 100 ? Math.round(value) : Math.round(value * 10) / 10
  return String(rounded).replace('.', ',')
}

/** Axis labels in so'm: 0, 850 ming, 1,2 mln, 3 mlrd. */
export function compactSom(tiyin: number): string {
  const som = tiyin / TIYIN_PER_SOM
  const abs = Math.abs(som)
  if (abs >= 1e9) return `${trim(som / 1e9)} mlrd`
  if (abs >= 1e6) return `${trim(som / 1e6)} mln`
  if (abs >= 1e3) return `${trim(som / 1e3)} ming`
  return trim(som)
}
