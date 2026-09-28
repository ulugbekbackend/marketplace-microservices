import type { SellerSubOrderDetail, SubOrderStatus } from '@bozorcha/api-client'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { routes } from '../routes'
import { panelApi, subOrderDetail } from '../test/fixtures'
import { apiError, json, renderWithApi, type Route } from '../test/renderApp'

const DETAIL = '/api/orders/seller/s1/'
const STATUS = '/api/orders/seller/s1/status/'

const plain = (text: string | null) => (text ?? '').replaceAll(String.fromCharCode(0xa0), ' ')

const at = (status: SubOrderStatus, patch: Partial<SellerSubOrderDetail> = {}) =>
  subOrderDetail({ status, ...patch })

function setup(order: SellerSubOrderDetail, api: Record<string, Route> = {}) {
  let current = order
  const handlers: Record<string, Route> = {
    ...panelApi,
    [`GET ${DETAIL}`]: () => json(200, current),
    [`PATCH ${STATUS}`]: (body) => {
      const { status, tracking_number, reason } = body as {
        status: SubOrderStatus
        tracking_number?: string
        reason?: string
      }
      current = {
        ...current,
        status,
        tracking_number: tracking_number ?? current.tracking_number,
        cancel_reason: reason ?? current.cancel_reason,
        history: [
          ...current.history,
          {
            from_status: current.status,
            to_status: status,
            reason: reason ?? '',
            created_at: '2026-09-27T10:00:00Z',
          },
        ],
      }
      return json(200, current)
    },
    ...api,
  }
  const view = renderWithApi(routes, handlers, '/orders/s1', { signedIn: true })
  return { ...view, setCurrent: (next: SellerSubOrderDetail) => (current = next) }
}

const actions = () => screen.queryByRole('group', { name: 'Buyurtma amallari' })
const buttonNames = () =>
  actions()
    ? within(actions()!)
        .getAllByRole('button')
        .map((b) => b.textContent)
    : []

describe('OrderDetailPage', () => {
  it('shows items, totals with commission, the customer and the history', async () => {
    setup(at('NEW'))
    expect(await screen.findByRole('heading', { name: 'Buyurtma #A1B2C3D4' })).toBeInTheDocument()
    expect(screen.getByText("Atlas ko'ylak (Qizil)")).toBeInTheDocument()
    expect(document.querySelector('img[src="https://img.test/atlas.webp"]')).not.toBeNull()
    expect(screen.getByText('Komissiya (10%)')).toBeInTheDocument()
    expect(plain(screen.getByTestId('order-net').textContent)).toBe("810 000 so'm")
    const call = screen.getByRole('link', { name: "Qo'ng'iroq qilish: +998 90 111 22 33" })
    expect(call).toHaveAttribute('href', 'tel:+998901112233')
    const history = screen.getByRole('list', { name: 'Holat tarixi' })
    const steps = within(history).getAllByRole('listitem')
    expect(steps.map((s) => s.textContent)).toEqual([
      expect.stringContaining('Yangi'),
      'Qabul qilinadi',
      "Jo'natiladi",
      'Yetkaziladi',
    ])
    expect(steps[0]).toHaveAttribute('aria-current', 'step')
  })

  it.each([
    ['NEW', ['Qabul qilish', 'Bekor qilish']],
    ['ACCEPTED', ["Jo'natish", 'Bekor qilish']],
    ['SHIPPED', ['Yetkazildi']],
    ['DELIVERED', []],
    ['CANCELLED_BY_SELLER', []],
  ] as const)('offers the right actions for %s', async (status, expected) => {
    setup(at(status, status === 'SHIPPED' ? { tracking_number: 'UZP1' } : {}))
    await screen.findByRole('heading', { name: 'Buyurtma #A1B2C3D4' })
    expect(buttonNames()).toEqual(expected)
  })

  it('hides the actions when the customer order is no longer active', async () => {
    setup(at('ACCEPTED', { order_status: 'REFUNDED' }))
    expect(await screen.findByText(/endi faol emas \(pul qaytarilgan\)/)).toBeInTheDocument()
    expect(actions()).not.toBeInTheDocument()
  })

  it('accepts a new order and refreshes the list and the stats', async () => {
    const u = userEvent.setup()
    const { callsTo } = setup(at('NEW'))
    await u.click(await screen.findByRole('button', { name: 'Qabul qilish' }))
    expect(await screen.findByText('Buyurtma qabul qilindi')).toBeInTheDocument()
    expect(callsTo('PATCH', STATUS)[0]![1]!.body).toBe(JSON.stringify({ status: 'ACCEPTED' }))
    expect(buttonNames()).toEqual(["Jo'natish", 'Bekor qilish'])
    await waitFor(() =>
      expect(callsTo('GET', '/api/orders/seller/stats/').length).toBeGreaterThanOrEqual(2),
    )
  })

  it('requires a tracking number to ship', async () => {
    const u = userEvent.setup()
    const { callsTo } = setup(at('ACCEPTED'))
    await u.click(await screen.findByRole('button', { name: "Jo'natish" }))
    const dialog = await screen.findByRole('dialog', { name: "Buyurtmani jo'natish" })
    await u.click(within(dialog).getByRole('button', { name: "Jo'natildi" }))
    expect(await within(dialog).findByText('Trek raqamini kiriting')).toBeInTheDocument()
    await u.type(within(dialog).getByLabelText('Trek raqami'), '   ')
    await u.click(within(dialog).getByRole('button', { name: "Jo'natildi" }))
    expect(callsTo('PATCH', STATUS)).toHaveLength(0)

    await u.clear(within(dialog).getByLabelText('Trek raqami'))
    await u.type(within(dialog).getByLabelText('Trek raqami'), ' UZP123456789 ')
    await u.click(within(dialog).getByRole('button', { name: "Jo'natildi" }))
    expect(await screen.findByText("Buyurtma jo'natildi")).toBeInTheDocument()
    expect(JSON.parse(String(callsTo('PATCH', STATUS)[0]![1]!.body))).toEqual({
      status: 'SHIPPED',
      tracking_number: 'UZP123456789',
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByTestId('next-step')).toHaveTextContent('Trek raqami: UZP123456789')
  })

  it('requires a reason of 1..255 characters to cancel', async () => {
    const u = userEvent.setup()
    const { callsTo } = setup(at('NEW'))
    await u.click(await screen.findByRole('button', { name: 'Bekor qilish' }))
    const dialog = await screen.findByRole('dialog', { name: 'Buyurtmani bekor qilasizmi?' })
    const confirm = within(dialog).getByRole('button', { name: 'Buyurtmani bekor qilish' })
    await u.click(confirm)
    expect(await within(dialog).findByText('Sababni yozing')).toBeInTheDocument()

    const reason = within(dialog).getByLabelText('Sabab')
    await u.click(reason)
    await u.paste('x'.repeat(256))
    await u.click(confirm)
    expect(await within(dialog).findByText('255 belgidan oshmasin')).toBeInTheDocument()
    expect(callsTo('PATCH', STATUS)).toHaveLength(0)

    await u.clear(reason)
    await u.type(reason, "O'lcham qolmadi")
    await u.click(confirm)
    expect(await screen.findByText('Buyurtma bekor qilindi')).toBeInTheDocument()
    expect(JSON.parse(String(callsTo('PATCH', STATUS)[0]![1]!.body))).toEqual({
      status: 'CANCELLED_BY_SELLER',
      reason: "O'lcham qolmadi",
    })
    expect(actions()).not.toBeInTheDocument()
    expect(screen.getByTestId('next-step')).toHaveTextContent('pul qaytariladi')
  })

  it('confirms delivery before sending it', async () => {
    const u = userEvent.setup()
    const { callsTo } = setup(at('SHIPPED', { tracking_number: 'UZP1' }))
    await u.click(await screen.findByRole('button', { name: 'Yetkazildi' }))
    const dialog = await screen.findByRole('dialog', { name: 'Buyurtma yetkazildimi?' })
    await u.click(within(dialog).getByRole('button', { name: 'Qoldirish' }))
    expect(callsTo('PATCH', STATUS)).toHaveLength(0)
    await u.click(screen.getByRole('button', { name: 'Yetkazildi' }))
    await u.click(await screen.findByRole('button', { name: 'Ha, yetkazildi' }))
    expect(await screen.findByText('Buyurtma yetkazildi deb belgilandi')).toBeInTheDocument()
  })

  it('explains a 409 and shows the fresh state', async () => {
    const u = userEvent.setup()
    const cancelled = at('CANCELLED_BY_SELLER', { cancel_reason: 'Boshqa oynada' })
    const { setCurrent, callsTo } = setup(at('NEW'), {
      [`PATCH ${STATUS}`]: () => {
        setCurrent(cancelled)
        return apiError(409, 'INVALID_TRANSITION', {
          from: 'CANCELLED_BY_SELLER',
          to: 'ACCEPTED',
        })
      },
    })
    await u.click(await screen.findByRole('button', { name: 'Qabul qilish' }))
    expect(await screen.findByText(/Buyurtma holati allaqachon o'zgargan/)).toBeInTheDocument()
    await waitFor(() => expect(actions()).not.toBeInTheDocument())
    expect(screen.getAllByText('Bekor qilingan').length).toBeGreaterThan(0)
    expect(callsTo('GET', DETAIL).length).toBeGreaterThanOrEqual(2)
  })

  it('explains an order that stopped being active', async () => {
    const u = userEvent.setup()
    setup(at('ACCEPTED'), {
      [`PATCH ${STATUS}`]: () => apiError(409, 'ORDER_NOT_ACTIVE', { order_status: 'REFUNDED' }),
    })
    await u.click(await screen.findByRole('button', { name: "Jo'natish" }))
    const dialog = await screen.findByRole('dialog')
    await u.type(within(dialog).getByLabelText('Trek raqami'), 'UZP1')
    await u.click(within(dialog).getByRole('button', { name: "Jo'natildi" }))
    expect(await screen.findByText(/buyurtmasi endi faol emas \(bekor/)).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('keeps the dialog open and marks the field on a 400', async () => {
    const u = userEvent.setup()
    setup(at('ACCEPTED'), {
      [`PATCH ${STATUS}`]: () =>
        apiError(400, 'VALIDATION_ERROR', { tracking_number: ['required'] }),
    })
    await u.click(await screen.findByRole('button', { name: "Jo'natish" }))
    const dialog = await screen.findByRole('dialog')
    await u.type(within(dialog).getByLabelText('Trek raqami'), 'UZP1')
    await u.click(within(dialog).getByRole('button', { name: "Jo'natildi" }))
    expect(await within(dialog).findByText('Trek raqamini kiriting')).toBeInTheDocument()
  })

  it('shows not found for foreign or unknown sub-orders', async () => {
    renderWithApi(
      routes,
      { ...panelApi, [`GET ${DETAIL}`]: () => apiError(404, 'NOT_FOUND') },
      '/orders/s1',
      { signedIn: true },
    )
    expect(await screen.findByText('Buyurtma topilmadi')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Buyurtmalarga qaytish' })).toHaveAttribute(
      'href',
      '/orders',
    )
  })
})
