import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { routes } from '../routes'
import { panelApi, subOrder } from '../test/fixtures'
import { apiError, json, renderWithApi, type Route } from '../test/renderApp'

const ORDERS = [
  subOrder(),
  subOrder({
    id: 's2',
    order_id: 'b41e0d7c-0000-4000-8000-000000000002',
    status: 'SHIPPED',
    customer_name: 'Jasur Toshmatov',
  }),
]

function setup(entry = '/orders', api: Record<string, Route> = {}) {
  const handlers: Record<string, Route> = {
    ...panelApi,
    'GET /api/orders/seller/': (_body, url) => {
      const status = url.searchParams.get('status')?.split(',') ?? []
      const items = status.length ? ORDERS.filter((o) => status.includes(o.status)) : ORDERS
      return json(200, { items, total: items.length, page: 1, page_size: 20 })
    },
    ...api,
  }
  return renderWithApi(routes, handlers, entry, { signedIn: true })
}

const lastListUrl = (callsTo: ReturnType<typeof setup>['callsTo']) =>
  new URL(String(callsTo('GET', '/api/orders/seller/').at(-1)![0]))

describe('OrdersPage', () => {
  it('lists sub-orders with number, customer, amounts and status', async () => {
    setup()
    const table = await screen.findByRole('table', { name: "Buyurtmalar ro'yxati" })
    const link = await within(table).findByRole('link', { name: '#A1B2C3D4' })
    expect(link).toHaveAttribute('href', '/orders/s1')
    expect(within(table).getAllByText('Aziza Karimova').length).toBeGreaterThan(0)
    expect(within(table).getAllByText('Yangi').length).toBeGreaterThan(0)
    expect(within(table).getAllByText("Jo'natilgan").length).toBeGreaterThan(0)
    expect(screen.getByText('2 ta buyurtma')).toBeInTheDocument()
  })

  it('shows per-status counts from the stats on the tabs', async () => {
    setup()
    expect(await screen.findByRole('tab', { name: /^Hammasi\W+11$/ })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    expect(screen.getByRole('tab', { name: /^Yangi\W+3$/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /^Bekor qilingan\W+1$/ })).toBeInTheDocument()
  })

  it('puts the status tab in the URL and the query', async () => {
    const u = userEvent.setup()
    const { router, callsTo } = setup()
    await screen.findByRole('link', { name: '#A1B2C3D4' })
    await u.click(await screen.findByRole('tab', { name: /^Jo'natilgan/ }))
    await waitFor(() => expect(router.state.location.search).toBe('?status=SHIPPED'))
    await waitFor(() => expect(lastListUrl(callsTo).searchParams.get('status')).toBe('SHIPPED'))
    await waitFor(() =>
      expect(screen.queryByRole('link', { name: '#A1B2C3D4' })).not.toBeInTheDocument(),
    )
    await u.click(screen.getByRole('tab', { name: /^Hammasi/ }))
    await waitFor(() => expect(router.state.location.search).toBe(''))
    await waitFor(() => expect(lastListUrl(callsTo).searchParams.has('status')).toBe(false))
  })

  it('filters by a date range through the URL and resets the page', async () => {
    const u = userEvent.setup()
    const { router, callsTo } = setup('/orders?status=NEW&page=2')
    await screen.findByRole('table')
    await u.type(screen.getByLabelText('Sanadan'), '2026-09-01')
    await waitFor(() => expect(router.state.location.search).toBe('?status=NEW&from=2026-09-01'))
    await u.type(screen.getByLabelText('Sanagacha'), '2026-09-27')
    await waitFor(() =>
      expect(router.state.location.search).toBe('?status=NEW&from=2026-09-01&to=2026-09-27'),
    )
    await waitFor(() => {
      const url = lastListUrl(callsTo)
      expect(Object.fromEntries(url.searchParams)).toEqual({
        status: 'NEW',
        date_from: '2026-09-01',
        date_to: '2026-09-27',
        page: '1',
        page_size: '20',
      })
    })
    await u.click(screen.getByRole('button', { name: 'Sanani tozalash' }))
    await waitFor(() => expect(router.state.location.search).toBe('?status=NEW'))
  })

  it('reads the page from the URL and links the other pages', async () => {
    const { callsTo } = setup('/orders?status=NEW&page=2', {
      'GET /api/orders/seller/': () =>
        json(200, { items: [subOrder()], total: 45, page: 2, page_size: 20 }),
    })
    await screen.findByRole('link', { name: '#A1B2C3D4' })
    expect(lastListUrl(callsTo).searchParams.get('page')).toBe('2')
    const nav = screen.getByRole('navigation', { name: 'Sahifalar' })
    expect(within(nav).getByRole('link', { name: '3-sahifa' })).toHaveAttribute(
      'href',
      '/orders?status=NEW&page=3',
    )
    expect(within(nav).getByRole('link', { name: '1-sahifa' })).toHaveAttribute(
      'href',
      '/orders?status=NEW',
    )
  })

  it('explains an empty shop and an empty filter differently', async () => {
    const u = userEvent.setup()
    const empty = {
      'GET /api/orders/seller/': () => json(200, { items: [], total: 0, page: 1, page_size: 20 }),
    }
    const { router } = setup('/orders?status=DELIVERED', empty)
    expect(await screen.findByText("Bu filtr bo'yicha buyurtma yo'q")).toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: 'Filtrni tozalash' }))
    await waitFor(() => expect(router.state.location.search).toBe(''))
    expect(await screen.findByText("Hali buyurtma yo'q")).toBeInTheDocument()
  })

  it('offers a retry on errors', async () => {
    setup('/orders', { 'GET /api/orders/seller/': () => apiError(500, 'SERVER_ERROR') })
    expect(await screen.findByRole('button', { name: 'Qayta urinish' })).toBeInTheDocument()
  })
})
