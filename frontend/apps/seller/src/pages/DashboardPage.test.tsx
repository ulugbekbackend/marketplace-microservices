import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { routes } from '../routes'
import { emptyStats, panelApi, sellerStats, subOrder } from '../test/fixtures'
import { apiError, json, renderWithApi, type Route } from '../test/renderApp'

// Recharts needs a laid-out DOM; the page's own table carries the numbers under test.
vi.mock('../components/RevenueChart', () => ({
  RevenueChart: ({ points }: { points: unknown[] }) => (
    <div data-testid="revenue-chart" data-points={points.length} />
  ),
}))

const plain = (text: string | null) => (text ?? '').replaceAll(String.fromCharCode(0xa0), ' ')

function setup(api: Record<string, Route> = {}) {
  return renderWithApi(routes, { ...panelApi, ...api }, '/', { signedIn: true })
}

describe('DashboardPage', () => {
  it('shows today, week and month with gross, net and order counts', async () => {
    setup()
    const cards = await screen.findAllByTestId('period-card')
    expect(cards).toHaveLength(3)
    const [today, week, month] = cards.map((card) => plain(card.textContent))
    expect(today).toContain('Bugun')
    expect(today).toContain('2 ta buyurtma')
    expect(today).toContain("900 000 so'm")
    expect(today).toContain("810 000 so'm")
    expect(week).toContain("2 250 000 so'm")
    expect(month).toContain("5 250 000 so'm")
    expect(month).toContain("4 725 000 so'm")
  })

  it('links the new orders count to the filtered list', async () => {
    setup()
    const callout = await screen.findByTestId('new-orders')
    expect(within(callout).getByText('3 ta yangi buyurtma')).toBeInTheDocument()
    expect(within(callout).getByRole('link', { name: "Yangilarini ko'rish" })).toHaveAttribute(
      'href',
      '/orders?status=NEW',
    )
    // The sidebar badge reads the same stats.
    const nav = screen.getAllByRole('link', { name: /Buyurtmalar/ })[0]!
    expect(nav).toHaveAccessibleName('Buyurtmalar, 3 ta yangi buyurtma')
  })

  it('maps the 30 days into the chart and its accessible table and summary', async () => {
    setup()
    const chart = await screen.findByTestId('revenue-chart')
    expect(chart).toHaveAttribute('data-points', '30')
    const table = screen.getByRole('table', { name: "Kunlik savdo jadvali, so'nggi 30 kun" })
    const rows = within(table).getAllByRole('row')
    expect(rows).toHaveLength(31)
    expect(plain(rows.at(-1)!.textContent)).toBe("27.09.20262900 000 so'm810 000 so'm")
    expect(plain(screen.getByTestId('chart-summary').textContent)).toBe(
      "So'nggi 30 kun: 5 ta buyurtma, tushum 2 250 000 so'm, sof daromad 2 025 000 so'm. Eng yaxshi kun: 26.09.2026.",
    )
  })

  it('lists the last five orders', async () => {
    const { callsTo } = setup({
      'GET /api/orders/seller/': () =>
        json(200, {
          items: [subOrder(), subOrder({ id: 's2', status: 'SHIPPED', customer_name: 'Jasur' })],
          total: 2,
          page: 1,
          page_size: 5,
        }),
    })
    const recent = await screen.findByRole('region', { name: "So'nggi buyurtmalar" })
    const link = await within(recent).findByRole('link', { name: /#A1B2C3D4.*Aziza Karimova/ })
    expect(link).toHaveAttribute('href', '/orders/s1')
    expect(within(recent).getByText("Jo'natilgan")).toBeInTheDocument()
    const url = new URL(String(callsTo('GET', '/api/orders/seller/')[0]![0]))
    expect(url.searchParams.get('page_size')).toBe('5')
  })

  it('welcomes a new seller with empty states instead of a flat chart', async () => {
    setup({ 'GET /api/orders/seller/stats/': () => json(200, emptyStats()) })
    expect(await screen.findByText("Hali savdo yo'q")).toBeInTheDocument()
    expect(screen.getByText("Yangi buyurtma yo'q")).toBeInTheDocument()
    expect(screen.getByText("Hali buyurtma yo'q")).toBeInTheDocument()
    expect(screen.queryByTestId('revenue-chart')).not.toBeInTheDocument()
    expect(screen.queryByTestId('nav-new-orders')).not.toBeInTheDocument()
    expect(plain(screen.getAllByTestId('period-card')[0]!.textContent)).toContain("0 so'm")
  })

  it('offers a retry when the stats fail', async () => {
    let fail = true
    const { callsTo } = setup({
      'GET /api/orders/seller/stats/': () =>
        fail ? apiError(500, 'SERVER_ERROR') : json(200, sellerStats()),
    })
    const retry = await screen.findAllByRole('button', { name: 'Qayta urinish' })
    fail = false
    retry[0]!.click()
    expect(await screen.findByTestId('new-orders')).toBeInTheDocument()
    await waitFor(() =>
      expect(callsTo('GET', '/api/orders/seller/stats/').length).toBeGreaterThanOrEqual(2),
    )
  })
})
