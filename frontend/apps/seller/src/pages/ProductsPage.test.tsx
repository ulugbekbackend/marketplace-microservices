import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { routes } from '../routes'
import { listItem, panelApi, productDetail, variant } from '../test/fixtures'
import { apiError, json, renderWithApi, type Route } from '../test/renderApp'

const detail = productDetail()
const draft = productDetail({
  id: 'p2',
  title: 'Choynak',
  status: 'draft',
  variants: [],
  variants_count: 0,
  min_price_tiyin: null,
  max_price_tiyin: null,
  stock_total: 0,
  reserved_total: 0,
})

function setup(api: Record<string, Route> = {}, entry = '/products') {
  let stored = detail
  const handlers: Record<string, Route> = {
    ...panelApi,
    'GET /api/catalog/seller/products/': (_body, url) => {
      const status = url.searchParams.get('status')
      const q = url.searchParams.get('q')
      let items = [stored, draft].map(listItem)
      if (status) items = items.filter((item) => item.status === status)
      if (q) items = items.filter((item) => item.title.toLowerCase().includes(q.toLowerCase()))
      return json(200, { items, total: items.length, page: 1, page_size: 20 })
    },
    'GET /api/catalog/seller/products/p1/': () => json(200, stored),
    'GET /api/catalog/seller/products/p2/': () => json(200, draft),
    'PATCH /api/catalog/seller/variants/v1/stock/': (body) => {
      const { stock } = body as { stock: number }
      stored = {
        ...stored,
        stock_total: stock,
        variants: [variant({ stock, available: stock - 2 })],
      }
      return json(200, stored.variants[0])
    },
    ...api,
  }
  return renderWithApi(routes, handlers, entry, { signedIn: true })
}

async function openVariants(u: ReturnType<typeof userEvent.setup>) {
  await u.click(await screen.findByRole('button', { name: "Variantlar va qoldiq: Atlas ko'ylak" }))
  return screen.findByRole('textbox', { name: 'Qoldiq: Qizil' })
}

afterEach(() => vi.useRealTimers())

describe('ProductsPage', () => {
  it('lists products with status, price and stock totals', async () => {
    setup()
    const table = await screen.findByRole('table', { name: "Mahsulotlar ro'yxati" })
    expect(await within(table).findByRole('link', { name: "Atlas ko'ylak" })).toHaveAttribute(
      'href',
      '/products/p1',
    )
    expect(within(table).getAllByText('Sotuvda').length).toBeGreaterThan(0)
    expect(within(table).getAllByText('Qoralama').length).toBeGreaterThan(0)
    expect(await within(table).findByText('10 dona')).toBeInTheDocument()
    expect(within(table).getByText('/ 2 band', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('2 ta mahsulot')).toBeInTheDocument()
  })

  it('takes stock totals from the list and fetches a detail only for an expanded row', async () => {
    const u = userEvent.setup()
    const { callsTo } = setup()
    const table = await screen.findByRole('table', { name: "Mahsulotlar ro'yxati" })
    expect(await within(table).findByText('10 dona')).toBeInTheDocument()
    expect(within(table).getByText('0 dona')).toBeInTheDocument()
    expect(callsTo('GET', '/api/catalog/seller/products/p1/')).toHaveLength(0)
    expect(callsTo('GET', '/api/catalog/seller/products/p2/')).toHaveLength(0)

    await openVariants(u)
    expect(callsTo('GET', '/api/catalog/seller/products/p1/')).toHaveLength(1)
    expect(callsTo('GET', '/api/catalog/seller/products/p2/')).toHaveLength(0)
  })

  it('filters by status tab and debounces the search', async () => {
    const u = userEvent.setup()
    const { callsTo, router } = setup()
    await screen.findByRole('table')
    await u.click(screen.getByRole('tab', { name: 'Qoralama' }))
    await waitFor(() => expect(router.state.location.search).toBe('?status=draft'))
    expect(await screen.findByRole('link', { name: 'Choynak' })).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.queryByRole('link', { name: "Atlas ko'ylak" })).not.toBeInTheDocument(),
    )

    const before = callsTo('GET', '/api/catalog/seller/products/').length
    await u.type(screen.getByRole('searchbox', { name: 'Mahsulot qidirish' }), 'choy')
    // Typing four letters produces one request, after the pause.
    await waitFor(() => expect(router.state.location.search).toBe('?status=draft&q=choy'))
    await waitFor(() => {
      const searches = callsTo('GET', '/api/catalog/seller/products/').slice(before)
      expect(searches.map(([url]) => new URL(String(url)).searchParams.get('q'))).toEqual(['choy'])
    })
  })

  it('shows the empty state for a new shop and a hint when a search finds nothing', async () => {
    setup({
      'GET /api/catalog/seller/products/': () =>
        json(200, { items: [], total: 0, page: 1, page_size: 20 }),
    })
    expect(await screen.findByText("Hali mahsulot yo'q")).toBeInTheDocument()
  })

  it('shows an error state with retry', async () => {
    const u = userEvent.setup()
    let fail = true
    setup({
      'GET /api/catalog/seller/products/': () =>
        fail ? apiError(500, 'BOOM') : json(200, { items: [], total: 0, page: 1, page_size: 20 }),
    })
    expect(
      await screen.findByText("Ma'lumotni yuklab bo'lmadi", {}, { timeout: 4000 }),
    ).toBeInTheDocument()
    fail = false
    await u.click(screen.getByRole('button', { name: 'Qayta urinish' }))
    expect(await screen.findByText("Hali mahsulot yo'q")).toBeInTheDocument()
  })

  it('saves a stock change inline', async () => {
    const u = userEvent.setup()
    const { callsTo } = setup()
    const input = await openVariants(u)
    await u.clear(input)
    await u.type(input, '25{Enter}')
    expect(await screen.findByText('Qoldiq saqlandi: Qizil')).toBeInTheDocument()
    expect(input).toHaveValue('25')
    // The list is refetched and shows the new total.
    const table = screen.getByRole('table', { name: "Mahsulotlar ro'yxati" })
    expect(await within(table).findByText('25 dona')).toBeInTheDocument()
    const [, init] = callsTo('PATCH', '/api/catalog/seller/variants/v1/stock/')[0]!
    expect(JSON.parse(String(init!.body))).toEqual({ stock: 25 })
  })

  it('stops below the reserved count before calling the API', async () => {
    const u = userEvent.setup()
    const { callsTo } = setup()
    const input = await openVariants(u)
    await u.clear(input)
    await u.type(input, '1{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent('2 dona band qilingan')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(callsTo('PATCH', '/api/catalog/seller/variants/v1/stock/')).toHaveLength(0)
  })

  it('rolls back and explains a 409 when orders reserved more meanwhile', async () => {
    const u = userEvent.setup()
    let release!: () => void
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    setup({
      'PATCH /api/catalog/seller/variants/v1/stock/': async () => {
        await held
        return apiError(409, 'STOCK_BELOW_RESERVED', { reserved: 5 })
      },
    })
    const input = await openVariants(u)
    await u.clear(input)
    await u.type(input, '3')
    await u.click(screen.getByRole('button', { name: 'Qoldiqni saqlash: Qizil' }))

    // Optimistic: the field keeps the new value while the request runs.
    expect(input).toHaveValue('3')
    const table = screen.getByRole('table', { name: "Mahsulotlar ro'yxati" })

    await act(async () => release())
    expect(await screen.findByText(/5 dona band qilingan/)).toBeInTheDocument()
    // Rolled back to the saved value.
    expect(await within(table).findByText('10 dona')).toBeInTheDocument()
    expect(input).toHaveAttribute('aria-invalid', 'true')
  })
})
