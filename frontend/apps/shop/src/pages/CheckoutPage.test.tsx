import type { Cart, CartItem } from '@bozorcha/api-client'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { apiError, json, renderWithApi, type Route } from '../test/renderApp'
import { CheckoutPage } from './CheckoutPage'

const plain = (text: string | null) => (text ?? '').replaceAll(String.fromCharCode(0xa0), ' ')

const line = (variantId: string, title: string, overrides: Partial<CartItem> = {}): CartItem => ({
  variant_id: variantId,
  product_id: `p-${variantId}`,
  product_slug: `slug-${variantId}`,
  title,
  sku: `SKU-${variantId}`,
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

const cart: Cart = {
  groups: [
    {
      seller_id: 's1',
      shop_name: 'Rishton sopol',
      items: [line('v1', 'Choynak', { qty: 2, line_total_tiyin: 200_000_00 })],
      subtotal_tiyin: 200_000_00,
    },
    {
      seller_id: 's2',
      shop_name: "Marg'ilon atlas",
      items: [line('v2', "Atlas ko'ylak")],
      subtotal_tiyin: 100_000_00,
    },
  ],
  total_tiyin: 300_000_00,
  items_count: 3,
  has_unavailable: false,
  has_price_changes: false,
  removed: [],
}

const me = { id: 'u1', phone: '+998901112233', full_name: 'Aziza Karimova', role: 'customer' }

const routes = [
  { path: '/checkout', element: <CheckoutPage /> },
  { path: '/login', element: <p>Kirish sahifasi</p> },
  { path: '/orders/:id', element: <p>Buyurtma sahifasi</p> },
  { path: '/cart', element: <p>Savatcha sahifasi</p> },
]

function setup(api: Record<string, Route> = {}, signedIn = true) {
  return renderWithApi(
    routes,
    {
      'GET /api/cart/': () => json(200, cart),
      'GET /api/auth/me/': () => json(200, me),
      ...api,
    },
    '/checkout',
    { signedIn },
  )
}

async function fillAddress(u: ReturnType<typeof userEvent.setup>) {
  await u.selectOptions(await screen.findByLabelText('Viloyat'), 'Toshkent shahri')
  await u.type(screen.getByLabelText('Shahar yoki tuman'), 'Toshkent')
  await u.type(screen.getByLabelText("Ko'cha, uy, xonadon"), 'Navoiy 12')
}

const submit = () => screen.getByRole('button', { name: 'Buyurtma berish' })

describe('CheckoutPage', () => {
  it('sends guests to login and back to checkout', async () => {
    const { router } = setup({}, false)
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(router.state.location.search).toBe('?next=%2Fcheckout')
  })

  it('shows the cart grouped by shop and prefills the profile', async () => {
    setup()
    const summary = await screen.findByRole('complementary', { name: 'Buyurtmangiz' })
    expect(within(summary).getByRole('region', { name: 'Rishton sopol' })).toBeInTheDocument()
    expect(within(summary).getAllByTestId('checkout-line')).toHaveLength(2)
    expect(plain(within(summary).getByTestId('checkout-total').textContent)).toBe("300 000 so'm")
    await waitFor(() =>
      expect(screen.getByLabelText('Qabul qiluvchi')).toHaveValue('Aziza Karimova'),
    )
    expect(screen.getByLabelText('Telefon raqam')).toHaveValue('90 111 22 33')
  })

  it('validates the address before calling the API', async () => {
    const u = userEvent.setup()
    const { callsTo } = setup({ 'GET /api/auth/me/': () => json(200, { ...me, full_name: '' }) })
    await u.click(await screen.findByRole('button', { name: 'Buyurtma berish' }))
    expect(await screen.findByText('Qabul qiluvchining ismini kiriting')).toBeInTheDocument()
    expect(screen.getByText('Viloyatni tanlang', { selector: 'p' })).toBeInTheDocument()
    expect(screen.getByText('Shahar yoki tumanni kiriting')).toBeInTheDocument()
    expect(screen.getByText('Manzilni kiriting')).toBeInTheDocument()
    await u.clear(screen.getByLabelText('Telefon raqam'))
    await u.type(screen.getByLabelText('Telefon raqam'), '9011')
    await u.click(submit())
    expect(await screen.findByText(/9 ta raqamdan/)).toBeInTheDocument()
    expect(callsTo('POST', '/api/orders/checkout/')).toHaveLength(0)
  })

  it('creates the order with an idempotency key and opens it', async () => {
    const u = userEvent.setup()
    const { callsTo, router } = setup({
      'POST /api/orders/checkout/': () => json(202, { order_id: 'o1', status: 'RESERVED' }),
    })
    await waitFor(() =>
      expect(screen.getByLabelText('Qabul qiluvchi')).toHaveValue('Aziza Karimova'),
    )
    await fillAddress(u)
    await u.type(screen.getByLabelText('Kuryer uchun izoh'), "Qo'ng'iroq qiling")
    await u.click(submit())
    await waitFor(() => expect(router.state.location.pathname).toBe('/orders/o1'))
    const [call] = callsTo('POST', '/api/orders/checkout/')
    const init = call![1]!
    expect(JSON.parse(String(init.body))).toEqual({
      address: {
        full_name: 'Aziza Karimova',
        phone: '+998901112233',
        region: 'Toshkent shahri',
        city: 'Toshkent',
        street: 'Navoiy 12',
        notes: "Qo'ng'iroq qiling",
      },
    })
    expect((init.headers as Record<string, string>)['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
  })

  it('reuses the same idempotency key when the user retries after a failure', async () => {
    const u = userEvent.setup()
    let attempts = 0
    const { callsTo, router } = setup({
      'POST /api/orders/checkout/': () =>
        ++attempts === 1
          ? apiError(500, 'HTTP_500')
          : json(202, { order_id: 'o9', status: 'RESERVED' }),
    })
    await waitFor(() =>
      expect(screen.getByLabelText('Qabul qiluvchi')).toHaveValue('Aziza Karimova'),
    )
    await fillAddress(u)
    await u.click(submit())
    expect(await screen.findByRole('alert')).toHaveTextContent(/Nimadir xato ketdi/)
    await u.click(submit())
    await waitFor(() => expect(router.state.location.pathname).toBe('/orders/o9'))
    const keys = callsTo('POST', '/api/orders/checkout/').map(
      ([, init]) => (init!.headers as Record<string, string>)['Idempotency-Key'],
    )
    expect(keys).toHaveLength(2)
    expect(keys[0]).toBe(keys[1])
  })

  it('names the unavailable items and blocks the submit once the cart is refetched', async () => {
    const u = userEvent.setup()
    let cartReads = 0
    const unavailableCart: Cart = {
      ...cart,
      has_unavailable: true,
      groups: [
        {
          ...cart.groups[0]!,
          items: [line('v1', 'Choynak', { qty: 2, available_qty: 1, available: false })],
        },
        cart.groups[1]!,
      ],
    }
    setup({
      'GET /api/cart/': () => json(200, ++cartReads === 1 ? cart : unavailableCart),
      'POST /api/orders/checkout/': () =>
        apiError(409, 'ITEMS_UNAVAILABLE', {
          items: [
            { variant_id: 'v1', reason: 'out_of_stock', available: 1 },
            { variant_id: 'v2', reason: 'inactive', available: 0 },
          ],
        }),
    })
    await waitFor(() =>
      expect(screen.getByLabelText('Qabul qiluvchi')).toHaveValue('Aziza Karimova'),
    )
    await fillAddress(u)
    await u.click(submit())
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Choynak: omborda 1 ta qoldi')
    expect(alert).toHaveTextContent("Atlas ko'ylak: sotuvdan olingan")
    await waitFor(() => expect(submit()).toBeDisabled())
    expect(screen.getByText("Ba'zi mahsulotlar sotuvda yo'q")).toBeInTheDocument()
  })

  it('shows an empty cart instead of the form', async () => {
    setup({
      'GET /api/cart/': () => json(200, { ...cart, groups: [], items_count: 0, total_tiyin: 0 }),
    })
    expect(await screen.findByRole('heading', { name: "Savatcha bo'sh" })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Buyurtma berish' })).not.toBeInTheDocument()
  })
})
