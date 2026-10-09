import { queryKeys, type Order, type OrderStatus } from '@bozorcha/api-client'
import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { leaveTo } from '../lib/redirect'
import { apiError, json, renderWithApi, type Route } from '../test/renderApp'
import { OrderPage } from './OrderPage'

vi.mock('../lib/redirect', async (original) => ({
  ...(await original<object>()),
  leaveTo: vi.fn(),
}))

const plain = (text: string | null) => (text ?? '').replaceAll(String.fromCharCode(0xa0), ' ')

const NOW = Date.parse('2026-09-27T10:00:00Z')
const iso = (ms: number) => new Date(ms).toISOString()

const baseOrder: Order = {
  id: 'a1b2c3d4-0000-4000-8000-000000000001',
  status: 'RESERVED',
  reserved_until: iso(NOW + 15 * 60_000),
  late_payment: false,
  total_tiyin: 300_000_00,
  cancel_reason: '',
  created_at: iso(NOW - 1000),
  updated_at: iso(NOW),
  delivery_address: {
    full_name: 'Aziza Karimova',
    phone: '+998901112233',
    region: 'Toshkent shahri',
    city: 'Toshkent',
    street: 'Navoiy 12',
    notes: 'Kechqurun',
  },
  history: [
    { from_status: null, to_status: 'PENDING', reason: '', created_at: iso(NOW - 1000) },
    { from_status: 'PENDING', to_status: 'RESERVED', reason: '', created_at: iso(NOW) },
  ],
  sellers: [
    {
      seller_id: 's1',
      shop_name: 'Rishton sopol',
      sub_order_id: null,
      cancel_reason: null,
      tracking_number: null,
      history: [],
      status: null,
      subtotal_tiyin: 200_000_00,
      items: [
        {
          id: 'i1',
          variant_id: 'v1',
          title: 'Choynak',
          sku: 'CH-1',
          image_url: null,
          qty: 2,
          price_tiyin: 100_000_00,
          line_total_tiyin: 200_000_00,
        },
      ],
    },
    {
      seller_id: 's2',
      shop_name: "Marg'ilon atlas",
      sub_order_id: null,
      cancel_reason: null,
      tracking_number: null,
      history: [],
      status: null,
      subtotal_tiyin: 100_000_00,
      items: [
        {
          id: 'i2',
          variant_id: 'v2',
          title: "Atlas ko'ylak",
          sku: 'AT-1',
          image_url: null,
          qty: 1,
          price_tiyin: 100_000_00,
          line_total_tiyin: 100_000_00,
        },
      ],
    },
  ],
}

const withStatus = (status: OrderStatus, extra: Partial<Order> = {}): Order => ({
  ...baseOrder,
  status,
  reserved_until: status === 'RESERVED' ? baseOrder.reserved_until : null,
  ...extra,
})

const ID = baseOrder.id
const DETAIL = `/api/orders/${ID}/`
const STATUS = `/api/orders/${ID}/status/`

const routes = [
  { path: '/orders/:orderId', element: <OrderPage /> },
  { path: '/orders/:orderId/payment', element: <p>To'lov natijasi</p> },
  { path: '/login', element: <p>Kirish sahifasi</p> },
]

function setup(api: Record<string, Route>, signedIn = true) {
  return renderWithApi(routes, api, `/orders/${ID}`, { signedIn })
}

const statusOf = (order: Order) => () =>
  json(200, { status: order.status, reserved_until: order.reserved_until })

afterEach(() => {
  vi.useRealTimers()
  vi.mocked(leaveTo).mockReset()
})

describe('OrderPage', () => {
  it('shows a reserved order: countdown, items per shop, totals, address and history', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(NOW)
    const order = withStatus('RESERVED')
    setup({ [`GET ${DETAIL}`]: () => json(200, order), [`GET ${STATUS}`]: statusOf(order) })

    expect(await screen.findByRole('heading', { name: 'Buyurtma #A1B2C3D4' })).toBeInTheDocument()
    const timer = screen.getByRole('timer', { name: "To'lov uchun qolgan vaqt" })
    expect(timer.textContent).toMatch(/^1[45]:\d\d$/)
    const methods = screen.getByRole('group', { name: "To'lov usuli" })
    expect(within(methods).getByRole('radio', { name: /Payme/ })).toBeChecked()
    expect(within(methods).getByRole('radio', { name: /Click/ })).not.toBeChecked()
    expect(screen.getByRole('button', { name: "Payme orqali to'lash" })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Buyurtmani bekor qilish' })).toBeInTheDocument()

    const rishton = screen.getByRole('region', { name: 'Rishton sopol' })
    expect(within(rishton).getByText('Choynak')).toBeInTheDocument()
    expect(plain(within(rishton).getByText(/2 ×/).textContent)).toBe("2 × 100 000 so'm")
    expect(plain(screen.getByTestId('order-total').textContent)).toBe("300 000 so'm")
    expect(screen.getByText('Navoiy 12')).toBeInTheDocument()
    const history = screen.getByRole('list', { name: 'Buyurtma tarixi' })
    expect(within(history).getAllByRole('listitem')).toHaveLength(2)
    expect(within(history).getByText("To'lov kutilmoqda")).toBeInTheDocument()
  })

  it('turns red near the deadline and refetches when the countdown reaches zero', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(NOW)
    const reserved = withStatus('RESERVED', { reserved_until: iso(NOW + 3000) })
    const expired = withStatus('EXPIRED', {
      cancel_reason: 'RESERVATION_EXPIRED',
      history: [
        ...baseOrder.history,
        {
          from_status: 'RESERVED',
          to_status: 'EXPIRED',
          reason: 'RESERVATION_EXPIRED',
          created_at: iso(NOW + 3000),
        },
      ],
    })
    let serverExpired = false
    const { callsTo } = setup({
      [`GET ${DETAIL}`]: () => json(200, serverExpired ? expired : reserved),
      // The server expires lazily: reads after the deadline report EXPIRED.
      [`GET ${STATUS}`]: () =>
        json(
          200,
          serverExpired
            ? { status: 'EXPIRED', reserved_until: null }
            : {
                status: 'RESERVED',
                reserved_until: reserved.reserved_until,
              },
        ),
    })
    const timer = await screen.findByRole('timer')
    expect(timer).toHaveTextContent('00:03')
    expect(timer).toHaveClass('text-danger-ink')
    const statusCallsBefore = callsTo('GET', STATUS).length

    serverExpired = true
    await act(() => vi.advanceTimersByTimeAsync(3500))
    await waitFor(() => expect(callsTo('GET', STATUS).length).toBeGreaterThan(statusCallsBefore))
    expect(await screen.findByText("To'lov vaqti tugadi")).toBeInTheDocument()
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: "Savatchaga o'tish" })).toHaveAttribute('href', '/cart')
  })

  it('polls a pending order until it is reserved', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(NOW)
    let reads = 0
    const { callsTo } = setup({
      [`GET ${DETAIL}`]: () =>
        json(200, reads >= 2 ? withStatus('RESERVED') : withStatus('PENDING')),
      [`GET ${STATUS}`]: () => {
        reads += 1
        return reads >= 2
          ? json(200, { status: 'RESERVED', reserved_until: baseOrder.reserved_until })
          : json(200, { status: 'PENDING', reserved_until: null })
      },
    })
    expect(await screen.findByText('Mahsulotlar band qilinmoqda')).toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(2100))
    expect(await screen.findByRole('timer')).toBeInTheDocument()
    const polls = callsTo('GET', STATUS).length
    await act(() => vi.advanceTimersByTimeAsync(10_000))
    expect(callsTo('GET', STATUS)).toHaveLength(polls)
  })

  it('starts a Click payment and sends the browser to the redirect URL', async () => {
    const u = userEvent.setup()
    const reserved = withStatus('RESERVED')
    const { callsTo } = setup({
      [`GET ${DETAIL}`]: () => json(200, reserved),
      [`GET ${STATUS}`]: statusOf(reserved),
      [`POST /api/payments/${ID}/init/`]: () =>
        json(200, { redirect_url: 'https://checkout.example/click' }),
    })
    await u.click(await screen.findByRole('radio', { name: /Click/ }))
    await u.click(screen.getByRole('button', { name: "Click orqali to'lash" }))

    await waitFor(() => expect(leaveTo).toHaveBeenCalledWith('https://checkout.example/click'))
    const [, init] = callsTo('POST', `/api/payments/${ID}/init/`)[0]!
    expect(JSON.parse(String(init?.body))).toEqual({ provider: 'click' })
  })

  it('pays with the test method and opens the result page', async () => {
    const u = userEvent.setup()
    const reserved = withStatus('RESERVED')
    const { queryClient, callsTo } = setup({
      [`GET ${DETAIL}`]: () => json(200, reserved),
      [`GET ${STATUS}`]: statusOf(reserved),
      [`POST /api/payments/mock/${ID}/pay`]: () =>
        json(200, { transaction_id: 't1', order_id: ID, amount_tiyin: reserved.total_tiyin }),
    })
    // the header's cart, cached before paying
    queryClient.setQueryData(queryKeys.cart, { items_count: 3 })
    await u.click(await screen.findByRole('radio', { name: /Test to'lov/ }))
    await u.click(screen.getByRole('button', { name: "Test to'lovini o'tkazish" }))

    expect(await screen.findByText("To'lov natijasi")).toBeInTheDocument()
    expect(callsTo('POST', `/api/payments/mock/${ID}/pay`)).toHaveLength(1)
    expect(callsTo('POST', `/api/orders/${ID}/pay/mock/`)).toHaveLength(0)
    expect(queryClient.getQueryState(queryKeys.cart)?.isInvalidated).toBe(true)
  })

  it('drops the test method when the server has mock payments off', async () => {
    const u = userEvent.setup()
    const reserved = withStatus('RESERVED')
    setup({
      [`GET ${DETAIL}`]: () => json(200, reserved),
      [`GET ${STATUS}`]: statusOf(reserved),
      [`POST /api/payments/mock/${ID}/pay`]: () => apiError(404, 'NOT_FOUND'),
    })
    await u.click(await screen.findByRole('radio', { name: /Test to'lov/ }))
    await u.click(screen.getByRole('button', { name: "Test to'lovini o'tkazish" }))

    expect(await screen.findByText("Test to'lovi bu muhitda o'chirilgan.")).toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: /Test to'lov/ })).not.toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Payme/ })).toBeChecked()
    expect(screen.getByRole('timer')).toBeInTheDocument()
  })

  it('cancels after confirmation', async () => {
    const u = userEvent.setup()
    const reserved = withStatus('RESERVED')
    const cancelled = withStatus('CANCELLED', { cancel_reason: 'CANCELLED_BY_CUSTOMER' })
    const { callsTo } = setup({
      [`GET ${DETAIL}`]: () => json(200, reserved),
      [`GET ${STATUS}`]: statusOf(reserved),
      [`POST /api/orders/${ID}/cancel/`]: () => json(200, cancelled),
    })
    await u.click(await screen.findByRole('button', { name: 'Buyurtmani bekor qilish' }))
    const dialog = await screen.findByRole('dialog', { name: 'Buyurtma bekor qilinsinmi?' })
    await u.click(within(dialog).getByRole('button', { name: 'Qoldirish' }))
    expect(callsTo('POST', `/api/orders/${ID}/cancel/`)).toHaveLength(0)

    await u.click(screen.getByRole('button', { name: 'Buyurtmani bekor qilish' }))
    await u.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Bekor qilish' }),
    )
    expect(await screen.findByText('Siz bekor qildingiz.')).toBeInTheDocument()
    expect(screen.getAllByText('Buyurtma bekor qilindi').length).toBeGreaterThan(0)
    expect(callsTo('POST', `/api/orders/${ID}/cancel/`)).toHaveLength(1)
  })

  it.each([
    ['CANCELLED', { cancel_reason: 'OUT_OF_STOCK' }, 'Mahsulot omborda qolmagan edi.'],
    ['COMPLETED', {}, 'Buyurtma yakunlandi'],
    ['REFUNDED', {}, "To'langan summa kartangizga qaytariladi."],
  ] as const)('renders %s', async (status, extra, text) => {
    const order = withStatus(status, extra)
    setup({ [`GET ${DETAIL}`]: () => json(200, order), [`GET ${STATUS}`]: statusOf(order) })
    expect(await screen.findByText(text)).toBeInTheDocument()
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Buyurtmani bekor qilish' }),
    ).not.toBeInTheDocument()
  })

  it('shows each shop its own timeline, tracking number and cancel reason', async () => {
    const at = (min: number) => iso(NOW + min * 60_000)
    const order = withStatus('FULFILLING', {
      sellers: [
        {
          ...baseOrder.sellers[0]!,
          sub_order_id: 'so1',
          status: 'SHIPPED',
          tracking_number: 'UZP123456789',
          history: [
            { from_status: null, to_status: 'NEW', reason: '', created_at: at(1) },
            { from_status: 'NEW', to_status: 'ACCEPTED', reason: '', created_at: at(2) },
            { from_status: 'ACCEPTED', to_status: 'SHIPPED', reason: '', created_at: at(3) },
          ],
        },
        {
          ...baseOrder.sellers[1]!,
          sub_order_id: 'so2',
          status: 'CANCELLED_BY_SELLER',
          cancel_reason: "O'lcham qolmadi",
          history: [
            { from_status: null, to_status: 'NEW', reason: '', created_at: at(1) },
            {
              from_status: 'NEW',
              to_status: 'CANCELLED_BY_SELLER',
              reason: "O'lcham qolmadi",
              created_at: at(4),
            },
          ],
        },
      ],
    })
    setup({ [`GET ${DETAIL}`]: () => json(200, order), [`GET ${STATUS}`]: statusOf(order) })

    const rishton = await screen.findByRole('region', { name: 'Rishton sopol' })
    const shipped = within(rishton).getByRole('list', { name: 'Rishton sopol: holat tarixi' })
    const steps = within(shipped).getAllByRole('listitem')
    expect(steps.map((step) => step.textContent)).toEqual([
      expect.stringContaining('Yangi'),
      expect.stringContaining('Qabul qilindi'),
      expect.stringContaining("Yo'lda"),
    ])
    expect(steps[2]).toHaveAttribute('aria-current', 'step')
    expect(within(rishton).getByTestId('tracking')).toHaveTextContent('UZP123456789')
    expect(within(rishton).queryByTestId('seller-cancelled')).not.toBeInTheDocument()

    const atlas = screen.getByRole('region', { name: "Marg'ilon atlas" })
    const note = within(atlas).getByTestId('seller-cancelled')
    expect(note).toHaveTextContent("Sabab: O'lcham qolmadi")
    expect(note).toHaveTextContent('Bu qism uchun pul qaytariladi.')
    expect(within(atlas).queryByTestId('tracking')).not.toBeInTheDocument()
    expect(within(atlas).getAllByRole('listitem').at(-1)!.textContent).toContain(
      'Sotuvchi bekor qildi',
    )
  })

  it('shows no sub-order timeline before payment', async () => {
    const order = withStatus('RESERVED')
    setup({ [`GET ${DETAIL}`]: () => json(200, order), [`GET ${STATUS}`]: statusOf(order) })
    await screen.findByRole('region', { name: 'Rishton sopol' })
    expect(screen.queryByRole('list', { name: /holat tarixi/ })).not.toBeInTheDocument()
  })

  it('shows not found for unknown or foreign orders', async () => {
    setup({
      [`GET ${DETAIL}`]: () => apiError(404, 'NOT_FOUND'),
      [`GET ${STATUS}`]: () => apiError(404, 'NOT_FOUND'),
    })
    expect(await screen.findByRole('heading', { name: 'Buyurtma topilmadi' })).toBeInTheDocument()
  })

  it('sends guests to login', async () => {
    const { router } = setup({}, false)
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(router.state.location.search).toBe(`?next=${encodeURIComponent(`/orders/${ID}`)}`)
  })

  it('rereads the order when the payment service says it can no longer be paid', async () => {
    const u = userEvent.setup()
    const reserved = withStatus('RESERVED')
    const { callsTo } = setup({
      [`GET ${DETAIL}`]: () => json(200, reserved),
      [`GET ${STATUS}`]: statusOf(reserved),
      [`POST /api/payments/${ID}/init/`]: () =>
        apiError(409, 'ORDER_NOT_PAYABLE', { status: 'EXPIRED' }),
    })
    await u.click(await screen.findByRole('button', { name: "Payme orqali to'lash" }))

    expect(
      await screen.findByText("Bu buyurtmani endi to'lab bo'lmaydi. Holatini yangiladik."),
    ).toBeInTheDocument()
    await waitFor(() => expect(callsTo('GET', STATUS).length).toBeGreaterThan(1))
    expect(leaveTo).not.toHaveBeenCalled()
  })

  it('shows a late payment as waiting and keeps polling until it settles', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(NOW)
    const late = withStatus('EXPIRED', { late_payment: true })
    const paid = withStatus('PAID', {
      late_payment: true,
      history: [
        ...baseOrder.history,
        {
          from_status: 'RESERVED',
          to_status: 'EXPIRED',
          reason: 'RESERVATION_EXPIRED',
          created_at: iso(NOW + 1000),
        },
        {
          from_status: 'EXPIRED',
          to_status: 'PAID',
          reason: 'LATE_PAYMENT',
          created_at: iso(NOW + 2000),
        },
      ],
    })
    let settled = false
    setup({
      [`GET ${DETAIL}`]: () => json(200, settled ? paid : late),
      [`GET ${STATUS}`]: () =>
        json(200, { status: settled ? 'PAID' : 'EXPIRED', reserved_until: null }),
    })
    expect(
      await screen.findByText("To'lov keldi, mahsulotlar qayta band qilinmoqda"),
    ).toBeInTheDocument()
    expect(screen.queryByText("To'lov vaqti tugadi")).not.toBeInTheDocument()

    settled = true
    await act(() => vi.advanceTimersByTimeAsync(2100))
    expect(await screen.findByText("To'lov qabul qilindi")).toBeInTheDocument()
    const history = screen.getByRole('list', { name: 'Buyurtma tarixi' })
    expect(
      within(history).getByText("To'lov muddatdan keyin keldi, mahsulotlar qayta band qilindi."),
    ).toBeInTheDocument()
  })

  it('explains a refund of a late payment whose items ran out', async () => {
    const refunded = withStatus('REFUNDED', {
      late_payment: true,
      history: [
        ...baseOrder.history,
        {
          from_status: 'RESERVED',
          to_status: 'EXPIRED',
          reason: 'RESERVATION_EXPIRED',
          created_at: iso(NOW + 1000),
        },
        {
          from_status: 'EXPIRED',
          to_status: 'REFUNDED',
          reason: 'LATE_PAYMENT_OUT_OF_STOCK',
          created_at: iso(NOW + 2000),
        },
      ],
    })
    setup({ [`GET ${DETAIL}`]: () => json(200, refunded), [`GET ${STATUS}`]: statusOf(refunded) })
    const text =
      "To'lov muddatdan keyin keldi, bu orada mahsulotlar tugagan. Pul to'liq qaytariladi."
    const panel = await screen.findByTestId('status-panel')
    expect(within(panel).getByText(text)).toBeInTheDocument()
    expect(
      within(screen.getByRole('list', { name: 'Buyurtma tarixi' })).getByText(text),
    ).toBeInTheDocument()
  })
})
