import { queryKeys, type Order, type OrderStatus } from '@bozorcha/api-client'
import { act, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiError, json, renderWithApi, type Route } from '../test/renderApp'
import { PaymentResultPage, SLOW_PAYMENT_MS } from './PaymentResultPage'

const ID = 'a1b2c3d4-0000-4000-8000-000000000001'
const DETAIL = `/api/orders/${ID}/`
const STATUS = `/api/orders/${ID}/status/`
const NOW = Date.parse('2026-10-09T10:00:00Z')

const order = (status: OrderStatus, extra: Partial<Order> = {}): Order => ({
  id: ID,
  status,
  reserved_until: status === 'RESERVED' ? new Date(NOW + 600_000).toISOString() : null,
  late_payment: false,
  total_tiyin: 100_000_00,
  cancel_reason: '',
  created_at: new Date(NOW).toISOString(),
  updated_at: new Date(NOW).toISOString(),
  delivery_address: {
    full_name: 'Aziza Karimova',
    phone: '+998901112233',
    region: 'Toshkent shahri',
    city: 'Toshkent',
    street: 'Navoiy 12',
    notes: '',
  },
  history: [],
  sellers: [],
  ...extra,
})

const routes = [
  { path: '/orders/:orderId/payment', element: <PaymentResultPage /> },
  { path: '/orders/:orderId', element: <p>Buyurtma sahifasi</p> },
  { path: '/login', element: <p>Kirish sahifasi</p> },
]

function setup(api: Record<string, Route>, provider = 'payme') {
  return renderWithApi(routes, api, `/orders/${ID}/payment?provider=${provider}`, {
    signedIn: true,
  })
}

afterEach(() => vi.useRealTimers())

describe('PaymentResultPage', () => {
  it('waits while the order is RESERVED, then shows the payment once it arrives', async () => {
    let current = order('RESERVED')
    const { queryClient } = setup({
      [`GET ${DETAIL}`]: () => json(200, current),
      [`GET ${STATUS}`]: () =>
        json(200, { status: current.status, reserved_until: current.reserved_until }),
    })
    queryClient.setQueryData(queryKeys.cart, { items_count: 1 })

    expect(await screen.findByRole('heading', { name: "Buyurtma #A1B2C3D4 to'lovi" })).toBeVisible()
    expect(queryClient.getQueryState(queryKeys.cart)?.isInvalidated).toBe(false)
    expect(screen.getByText('Payme orqali')).toBeInTheDocument()
    expect(screen.getByText("To'lov tasdiqlanishini kutyapmiz")).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Buyurtmaga qaytish' })).toHaveAttribute(
      'href',
      `/orders/${ID}`,
    )

    current = order('PAID')
    expect(await screen.findByText("To'lov qabul qilindi", {}, { timeout: 5000 })).toBeVisible()
    expect(screen.getByRole('link', { name: "Buyurtmani ko'rish" })).toBeInTheDocument()
    // the order service emptied the cart when the payment landed
    expect(queryClient.getQueryState(queryKeys.cart)?.isInvalidated).toBe(true)
  })

  it('suggests going back after a minute without a confirmation', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(NOW)
    const reserved = order('RESERVED')
    setup(
      {
        [`GET ${DETAIL}`]: () => json(200, reserved),
        [`GET ${STATUS}`]: () =>
          json(200, { status: reserved.status, reserved_until: reserved.reserved_until }),
      },
      'click',
    )
    expect(await screen.findByText("To'lov tasdiqlanishini kutyapmiz")).toBeInTheDocument()
    expect(screen.getByText('Click orqali')).toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(SLOW_PAYMENT_MS + 100)
    })

    expect(screen.getByText("To'lov hali tasdiqlanmadi")).toBeInTheDocument()
  })

  it.each([
    ['EXPIRED', "To'lov vaqti tugadi"],
    ['REFUNDED', 'Pul qaytarildi'],
  ] as const)('explains a %s order', async (status, title) => {
    const settled = order(status)
    setup({
      [`GET ${DETAIL}`]: () => json(200, settled),
      [`GET ${STATUS}`]: () => json(200, { status, reserved_until: null }),
    })

    expect(await screen.findByText(title)).toBeInTheDocument()
  })

  it('shows the late payment wait for an EXPIRED order that was paid late', async () => {
    const late = order('EXPIRED', { late_payment: true })
    setup({
      [`GET ${DETAIL}`]: () => json(200, late),
      [`GET ${STATUS}`]: () => json(200, { status: 'EXPIRED', reserved_until: null }),
    })

    expect(
      await screen.findByText("To'lov keldi, mahsulotlar qayta band qilinmoqda"),
    ).toBeInTheDocument()
  })

  it('ignores an unknown provider in the URL', async () => {
    const paid = order('PAID')
    setup(
      {
        [`GET ${DETAIL}`]: () => json(200, paid),
        [`GET ${STATUS}`]: () => json(200, { status: 'PAID', reserved_until: null }),
      },
      'paypal',
    )

    expect(await screen.findByText("To'lov qabul qilindi")).toBeInTheDocument()
    expect(screen.queryByText(/orqali$/)).not.toBeInTheDocument()
  })

  it("shows not found for an order that is not the customer's", async () => {
    setup({ [`GET ${DETAIL}`]: () => apiError(404, 'NOT_FOUND') })

    expect(await screen.findByRole('heading', { name: 'Buyurtma topilmadi' })).toBeInTheDocument()
  })
})
