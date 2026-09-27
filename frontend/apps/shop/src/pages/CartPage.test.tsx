import type { Cart, CartItem } from '@bozorcha/api-client'
import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { apiError, json, renderWithApi, type Route } from '../test/renderApp'
import { CartPage } from './CartPage'

const plain = (text: string | null) => (text ?? '').replaceAll(String.fromCharCode(0xa0), ' ')

const line = (overrides: Partial<CartItem> & Pick<CartItem, 'variant_id'>): CartItem => ({
  product_id: `p-${overrides.variant_id}`,
  product_slug: `slug-${overrides.variant_id}`,
  title: `Mahsulot ${overrides.variant_id}`,
  sku: `SKU-${overrides.variant_id}`,
  image_url: null,
  attributes: [],
  qty: 1,
  price_tiyin: 100_000_00,
  line_total_tiyin: 100_000_00,
  available_qty: 10,
  available: true,
  price_changed: false,
  previous_price_tiyin: null,
  ...overrides,
})

const choynak = line({
  variant_id: 'v1',
  title: 'Choynak',
  product_slug: 'choynak',
  attributes: [{ code: 'color', name: 'Rang', value: "Ko'k" }],
  qty: 2,
  price_tiyin: 120_000_00,
  line_total_tiyin: 240_000_00,
})
const piyola = line({
  variant_id: 'v2',
  title: 'Piyola',
  price_tiyin: 30_000_00,
  line_total_tiyin: 30_000_00,
  price_changed: true,
  previous_price_tiyin: 25_000_00,
})
const atlas = line({
  variant_id: 'v3',
  title: "Atlas ko'ylak",
  qty: 3,
  available_qty: 1,
  available: false,
  line_total_tiyin: 300_000_00,
})
const sold = line({ variant_id: 'v4', title: 'Do‘ppi', available_qty: 0, available: false })

const fullCart: Cart = {
  groups: [
    {
      seller_id: 's1',
      shop_name: 'Rishton sopol',
      items: [choynak, piyola],
      subtotal_tiyin: 270_000_00,
    },
    { seller_id: 's2', shop_name: "Marg'ilon atlas", items: [atlas, sold], subtotal_tiyin: 0 },
  ],
  total_tiyin: 270_000_00,
  items_count: 7,
  has_unavailable: true,
  has_price_changes: true,
  removed: ['gone-1'],
}

const cleanCart: Cart = {
  groups: [fullCart.groups[0]!],
  total_tiyin: 270_000_00,
  items_count: 3,
  has_unavailable: false,
  has_price_changes: false,
  removed: [],
}

const emptyCart: Cart = {
  groups: [],
  total_tiyin: 0,
  items_count: 0,
  has_unavailable: false,
  has_price_changes: false,
  removed: [],
}

const routes = [
  { path: '/cart', element: <CartPage /> },
  { path: '/login', element: <p>Kirish sahifasi</p> },
  { path: '/checkout', element: <p>Rasmiylashtirish sahifasi</p> },
  { path: '/p/:slug', element: <p>Mahsulot sahifasi</p> },
]

function setup(api: Record<string, Route>) {
  return renderWithApi(routes, api, '/cart')
}

describe('CartPage', () => {
  it('groups lines by shop with subtotals, total and status marks', async () => {
    setup({ 'GET /api/cart/': () => json(200, fullCart) })

    const rishton = await screen.findByRole('region', { name: 'Rishton sopol' })
    const margilon = screen.getByRole('region', { name: "Marg'ilon atlas" })
    expect(within(rishton).getAllByTestId('cart-line')).toHaveLength(2)
    expect(within(margilon).getAllByTestId('cart-line')).toHaveLength(2)
    expect(plain(rishton.textContent)).toContain("Do'kon bo'yicha: 270 000 so'm")
    expect(plain(screen.getByTestId('cart-total').textContent)).toBe("270 000 so'm")
    expect(screen.getByText('7 ta mahsulot')).toBeInTheDocument()

    // title links to the product, attributes are listed
    expect(within(rishton).getByRole('link', { name: 'Choynak' })).toHaveAttribute(
      'href',
      '/p/choynak',
    )
    expect(within(rishton).getByText("Rang: Ko'k")).toBeInTheDocument()

    // price change: old -> new
    const change = within(rishton).getByTestId('price-change')
    expect(plain(change.textContent)).toBe("Oldingi narx: 25 000 so'mYangi narx: 30 000 so'm")
    expect(within(rishton).getByText("Narx o'zgardi")).toBeInTheDocument()

    // unavailable: not enough stock / sold out
    expect(within(margilon).getByText('Omborda 1 ta qoldi')).toBeInTheDocument()
    expect(within(margilon).getByText("Sotuvda yo'q")).toBeInTheDocument()
    const soldStepper = within(margilon).getByRole('spinbutton', { name: 'Do‘ppi: soni' })
    expect(soldStepper).toBeDisabled()

    // notices and a blocked checkout
    expect(screen.getByText(/Sotuvdan olingan 1 ta mahsulot/)).toBeInTheDocument()
    expect(screen.getByText(/narxi siz qo'shgandan beri o'zgardi/)).toBeInTheDocument()
    const checkout = screen.getByRole('button', { name: 'Rasmiylashtirish' })
    expect(checkout).toBeDisabled()
    expect(checkout).toHaveAccessibleDescription(/Sotuvda yo'q mahsulotlarni olib tashlang/)
  })

  it('limits a short line to the units left', async () => {
    const u = userEvent.setup()
    const patches: unknown[] = []
    setup({
      'GET /api/cart/': () => json(200, fullCart),
      'PATCH /api/cart/items/v3/': (body) => {
        patches.push(body)
        return json(200, fullCart)
      },
    })
    const margilon = await screen.findByRole('region', { name: "Marg'ilon atlas" })
    const stepper = within(margilon).getByRole('spinbutton', { name: "Atlas ko'ylak: soni" })
    expect(stepper).toHaveAttribute('aria-valuemax', '1')
    const [decrease] = within(margilon).getAllByRole('button', { name: 'Kamaytirish' })
    await u.click(decrease!)
    expect(patches).toEqual([{ qty: 1 }])
  })

  it('changes the quantity and shows the cart the server returns', async () => {
    const u = userEvent.setup()
    const patches: unknown[] = []
    const updated: Cart = {
      ...cleanCart,
      groups: [
        {
          ...cleanCart.groups[0]!,
          items: [{ ...choynak, qty: 3, line_total_tiyin: 360_000_00 }, piyola],
          subtotal_tiyin: 390_000_00,
        },
      ],
      total_tiyin: 390_000_00,
      items_count: 4,
    }
    setup({
      'GET /api/cart/': () => json(200, cleanCart),
      'PATCH /api/cart/items/v1/': (body) => {
        patches.push(body)
        return json(200, updated)
      },
    })
    const stepper = await screen.findByRole('spinbutton', { name: 'Choynak: soni' })
    const lineEl = stepper.closest('li')!
    await u.click(within(lineEl).getByRole('button', { name: "Ko'paytirish" }))
    expect(patches).toEqual([{ qty: 3 }])
    await waitFor(() =>
      expect(plain(screen.getByTestId('cart-total').textContent)).toBe("390 000 so'm"),
    )
    expect(stepper).toHaveValue('3')
    expect(plain(within(lineEl).getByTestId('line-total').textContent)).toBe("360 000 so'm")
  })

  it('reports a failed quantity change and restores the line', async () => {
    const u = userEvent.setup()
    setup({
      'GET /api/cart/': () => json(200, cleanCart),
      'PATCH /api/cart/items/v1/': () => apiError(409, 'OUT_OF_STOCK', { available: 2 }),
    })
    const stepper = await screen.findByRole('spinbutton', { name: 'Choynak: soni' })
    await u.click(within(stepper.closest('li')!).getByRole('button', { name: "Ko'paytirish" }))
    expect(await screen.findByText('Omborda yetarli emas: faqat 2 ta bor.')).toBeInTheDocument()
    await waitFor(() => expect(stepper).toHaveValue('2'))
  })

  it('removes a line and clears the cart after confirmation', async () => {
    const u = userEvent.setup()
    const single: Cart = {
      ...cleanCart,
      groups: [{ ...cleanCart.groups[0]!, items: [choynak], subtotal_tiyin: 240_000_00 }],
      total_tiyin: 240_000_00,
      items_count: 2,
    }
    let cleared = false
    setup({
      'GET /api/cart/': () => json(200, cleanCart),
      'DELETE /api/cart/items/v2/': () => json(200, single),
      'DELETE /api/cart/': () => {
        cleared = true
        return new Response(null, { status: 204 })
      },
    })
    await u.click(await screen.findByRole('button', { name: "Piyola: savatchadan o'chirish" }))
    await waitFor(() => expect(screen.queryByText('Piyola')).not.toBeInTheDocument())
    expect(screen.getByText('2 ta mahsulot')).toBeInTheDocument()

    await u.click(screen.getByRole('button', { name: 'Savatchani tozalash' }))
    const dialog = await screen.findByRole('dialog', { name: 'Savatcha tozalansinmi?' })
    await u.click(within(dialog).getByRole('button', { name: 'Tozalash' }))
    expect(await screen.findByRole('heading', { name: "Savatcha bo'sh" })).toBeInTheDocument()
    expect(cleared).toBe(true)
    expect(screen.getByRole('link', { name: "Katalogga o'tish" })).toHaveAttribute(
      'href',
      '/catalog',
    )
  })

  it('sends guests to login before checkout, signed-in users straight on', async () => {
    const u = userEvent.setup()
    const { router, client } = setup({ 'GET /api/cart/': () => json(200, cleanCart) })
    await u.click(await screen.findByRole('button', { name: 'Rasmiylashtirish' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(router.state.location.search).toBe('?next=%2Fcheckout')

    act(() => client.tokens.set({ access: 'a1', refresh: 'r1' }))
    await act(() => router.navigate('/cart'))
    await u.click(await screen.findByRole('button', { name: 'Rasmiylashtirish' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/checkout'))
  })

  it('shows the empty state', async () => {
    setup({ 'GET /api/cart/': () => json(200, emptyCart) })
    expect(await screen.findByRole('heading', { name: "Savatcha bo'sh" })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Rasmiylashtirish' })).not.toBeInTheDocument()
  })

  it('shows an error with retry', async () => {
    const u = userEvent.setup()
    let calls = 0
    setup({
      'GET /api/cart/': () =>
        ++calls === 1 ? apiError(503, 'CATALOG_UNAVAILABLE') : json(200, cleanCart),
    })
    await u.click(await screen.findByRole('button', { name: 'Qayta urinish' }))
    expect(await screen.findByRole('region', { name: 'Rishton sopol' })).toBeInTheDocument()
  })
})
