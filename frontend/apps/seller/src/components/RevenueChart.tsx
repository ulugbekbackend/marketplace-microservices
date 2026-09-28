import { formatPrice } from '@bozorcha/ui'
import { useTranslation } from 'react-i18next'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { compactSom, dayLabelLong, type ChartPoint } from '../lib/stats'

const GROSS = 'var(--color-chart-gross)'
const NET = 'var(--color-chart-net)'
const MUTED = 'var(--color-text-muted)'

type TooltipArgs = { active?: boolean; payload?: ReadonlyArray<{ payload?: unknown }> }

function ChartTooltip({ active, payload }: TooltipArgs) {
  const { t } = useTranslation()
  const point = payload?.[0]?.payload as ChartPoint | undefined
  if (!active || !point) return null
  return (
    <div className="min-w-44 rounded-lg border border-border bg-surface px-3 py-2 text-sm shadow-soft">
      <p className="font-semibold text-text tabular">{dayLabelLong(point.date)}</p>
      <p className="text-xs text-text-muted tabular">
        {t('dashboard.ordersCount', { count: point.orders })}
      </p>
      <dl className="mt-1.5 flex flex-col gap-1 tabular">
        <div className="flex items-center justify-between gap-4">
          <dt className="flex items-center gap-1.5 text-text-muted">
            <span aria-hidden="true" className="h-0.5 w-3 rounded-full bg-chart-gross" />
            {t('dashboard.gross')}
          </dt>
          <dd className="font-semibold text-text">{formatPrice(point.gross)}</dd>
        </div>
        <div className="flex items-center justify-between gap-4">
          <dt className="flex items-center gap-1.5 text-text-muted">
            <span aria-hidden="true" className="h-0.5 w-3 rounded-full bg-chart-net" />
            {t('dashboard.net')}
          </dt>
          <dd className="font-semibold text-text">{formatPrice(point.net)}</dd>
        </div>
      </dl>
    </div>
  )
}

/**
 * Gross vs net per day, one money axis. Purely visual: the page renders the same numbers as a
 * table for assistive technology, so the SVG is hidden from it and not keyboard focusable.
 */
export function RevenueChart({ points }: { points: ChartPoint[] }) {
  return (
    <div aria-hidden="true" className="h-56 w-full sm:h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={points}
          margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
          accessibilityLayer={false}
        >
          <CartesianGrid vertical={false} stroke="var(--color-border)" strokeDasharray="3 3" />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={{ stroke: 'var(--color-border)' }}
            tick={{ fill: MUTED, fontSize: 12 }}
            interval="preserveStartEnd"
            minTickGap={24}
            tickMargin={8}
          />
          <YAxis
            width={64}
            tickLine={false}
            axisLine={false}
            tick={{ fill: MUTED, fontSize: 12 }}
            tickFormatter={(value: number) => compactSom(value)}
            allowDecimals={false}
          />
          <Tooltip
            cursor={{ stroke: 'var(--color-border-strong)', strokeWidth: 1 }}
            content={(props) => <ChartTooltip active={props.active} payload={props.payload} />}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="gross"
            stroke={GROSS}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, stroke: 'var(--color-surface)', strokeWidth: 2, fill: GROSS }}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="net"
            stroke={NET}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, stroke: 'var(--color-surface)', strokeWidth: 2, fill: NET }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
