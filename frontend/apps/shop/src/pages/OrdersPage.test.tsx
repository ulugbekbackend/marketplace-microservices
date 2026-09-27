import type { OrderSummary } from '@bozorcha/api-client'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { apiError, json, renderWithApi, type Route } from '../test/renderApp'
import { OrdersPage } from './OrdersPage'

const plain = (text: string | null) => (text ?? '').replaceAll(String.fromCharCode(0xa0), ' ')

const summary = (n: number, status: OrderSummary['status']): OrderSummary => ({
  id: `${String(n).padStart(8, '0')}-0000-4000-8000-000000000000`,
  status,
  total_tiyin: n * 100_000_00,
  items_count: n,
  reserved_until: null,
  created_at: '2026-09-27T10:00:00Z',
})

const routes = [
  { path: '/orders', element: <OrdersPage /> },
  { path: '/orders/:id', element: <p>Buyurtma sahifasi</p> },
  { path: '/login', element: <p>Kirish sahifasi</p> },
]

function setup(api: Record<string, Route>, entry = '/orders', signedIn = true) {
  return renderWithApi(routes, api, entry, { signedIn })
}

describe('OrdersPage', () => {
  it('lists orders with status, total, date and item count, each linking to its page', async () => {
    const u = userEvent.setup()
    const { router } = setup({
      'GET /api/orders/': () =>
        json(200, {
          items: [summary(1, 'RESERVED'), summary(2, 'PAID'), summary(3, 'CANCELLED')],
          total: 3,
          page: 1,
          page_size: 10,
        }),
    })
    const list = await screen.findByRole('list', { name: "Buyurtmalar ro'yxati" })
    const rows = within(list).getAllByTestId('order-row')
    expect(rows).toHaveLength(3)
    expect(rows[0]).toHaveAccessibleName(
      /^#00000001 \d\d\.\d\d\.\d{4}, \d\d:\d\d, 1 ta mahsulot To'lov kutilmoqda 100.000.so'm$/,
    )
    expect(plain(rows[1]!.textContent)).toContain("200 000 so'm")
    expect(rows[1]).toHaveTextContent('2 ta mahsulot')
    expect(rows[2]).toHaveTextContent('Bekor qilindi')
    expect(
      screen.queryByRole('navigation', { name: 'Buyurtmalar sahifalari' }),
    ).not.toBeInTheDocument()

    await u.click(rows[0]!)
    await waitFor(() =>
      expect(router.state.location.pathname).toBe('/orders/00000001-0000-4000-8000-000000000000'),
    )
  })

  it('pages through long histories', async () => {
    const pages: string[] = []
    setup(
      {
        'GET /api/orders/': (_body, url) => {
          pages.push(url.searchParams.get('page') ?? '')
          return json(200, {
            items: [summary(11, 'COMPLETED')],
            total: 25,
            page: 2,
            page_size: 10,
          })
        },
      },
      '/orders?page=2',
    )
    const nav = await screen.findByRole('navigation', { name: 'Buyurtmalar sahifalari' })
    expect(within(nav).getByRole('link', { name: '3-sahifa' })).toHaveAttribute(
      'href',
      '/orders?page=3',
    )
    expect(pages).toEqual(['2'])
  })

  it('shows the empty state', async () => {
    setup({ 'GET /api/orders/': () => json(200, { items: [], total: 0, page: 1, page_size: 10 }) })
    expect(await screen.findByRole('heading', { name: "Hali buyurtma yo'q" })).toBeInTheDocument()
  })

  it('offers retry on errors and sends guests to login', async () => {
    const u = userEvent.setup()
    let calls = 0
    setup({
      'GET /api/orders/': () =>
        ++calls === 1
          ? apiError(503, 'SERVICE_UNAVAILABLE')
          : json(200, { items: [summary(1, 'PAID')], total: 1, page: 1, page_size: 10 }),
    })
    await u.click(await screen.findByRole('button', { name: 'Qayta urinish' }))
    expect(await screen.findAllByTestId('order-row')).toHaveLength(1)
  })

  it('redirects guests', async () => {
    const { router } = setup({}, '/orders', false)
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(router.state.location.search).toBe('?next=%2Forders')
  })
})
