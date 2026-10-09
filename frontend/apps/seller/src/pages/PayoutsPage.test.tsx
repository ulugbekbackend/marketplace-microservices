import type { SellerPayout } from '@bozorcha/api-client'
import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { payoutWeek, payoutWeekShort, readPage } from '../lib/payouts'
import { routes } from '../routes'
import { panelApi } from '../test/fixtures'
import { apiError, json, renderWithApi, type Route } from '../test/renderApp'

const plain = (text: string | null) => (text ?? '').replaceAll(String.fromCharCode(0xa0), ' ')

const payout = (overrides: Partial<SellerPayout> = {}): SellerPayout => ({
  id: 'p1',
  period_start: '2026-09-28',
  period_end: '2026-10-05',
  gross_tiyin: 1_200_000_00,
  commission_tiyin: 120_000_00,
  net_tiyin: 1_080_000_00,
  status: 'pending',
  lines_count: 3,
  created_at: '2026-10-05T01:00:00Z',
  ...overrides,
})

const PAYOUTS = '/api/payments/seller/payouts/'

function setup(entry = '/payouts', api: Record<string, Route> = {}) {
  return renderWithApi(
    routes,
    {
      ...panelApi,
      [`GET ${PAYOUTS}`]: () =>
        json(200, {
          items: [
            payout(),
            payout({
              id: 'p0',
              period_start: '2026-09-21',
              period_end: '2026-09-28',
              status: 'paid',
              lines_count: 1,
              net_tiyin: 90_000_00,
            }),
          ],
          total: 2,
          page: 1,
          page_size: 20,
        }),
      ...api,
    },
    entry,
    { signedIn: true },
  )
}

describe('payout helpers', () => {
  it('shows the week up to the Sunday before period_end', () => {
    expect(payoutWeek('2026-09-28', '2026-10-05')).toEqual({ from: '28.09.2026', to: '04.10.2026' })
    expect(payoutWeek('2026-12-28', '2027-01-04')).toEqual({ from: '28.12.2026', to: '03.01.2027' })
  })

  it('shortens the week for narrow screens', () => {
    expect(payoutWeekShort('2026-09-21', '2026-09-28')).toBe('21–27.09.2026')
    expect(payoutWeekShort('2026-08-31', '2026-09-07')).toBe('31.08–06.09.2026')
    expect(payoutWeekShort('2026-12-28', '2027-01-04')).toBe('28.12.2026–03.01.2027')
  })

  it('reads the page number from the URL', () => {
    expect(readPage(new URLSearchParams('page=3'))).toBe(3)
    expect(readPage(new URLSearchParams('page=0'))).toBe(1)
    expect(readPage(new URLSearchParams('page=x'))).toBe(1)
  })
})

describe('PayoutsPage', () => {
  it('lists weekly payouts with amounts and status', async () => {
    setup()

    const table = await screen.findByRole('table', { name: "Haftalik to'lovlar" })
    expect(await within(table).findByText('28.09.2026 – 04.10.2026')).toBeInTheDocument()
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    expect(plain(within(rows[0]!).getAllByText(/1 080 000/)[0]!.textContent)).toBe("1 080 000 so'm")
    expect(within(rows[0]!).getAllByText("To'lanishi kutilmoqda").length).toBeGreaterThan(0)
    expect(within(rows[1]!).getAllByText("To'landi").length).toBeGreaterThan(0)
    expect(screen.getByText('2 ta hafta')).toBeInTheDocument()
  })

  it('is reachable from the menu', async () => {
    setup('/')

    const link = await screen.findAllByRole('link', { name: "To'lovlar" })
    expect(link[0]).toHaveAttribute('href', '/payouts')
  })

  it('asks for the page in the URL', async () => {
    const { callsTo } = setup('/payouts?page=2')

    await screen.findByRole('table', { name: "Haftalik to'lovlar" })
    const url = new URL(String(callsTo('GET', PAYOUTS).at(-1)![0]))
    expect(url.searchParams.get('page')).toBe('2')
    expect(url.searchParams.get('page_size')).toBe('20')
  })

  it('explains when payouts will appear', async () => {
    setup('/payouts', {
      [`GET ${PAYOUTS}`]: () => json(200, { items: [], total: 0, page: 1, page_size: 20 }),
    })

    expect(await screen.findByText("Hali to'lovlar yo'q")).toBeInTheDocument()
  })

  it('offers a retry when the payouts cannot be loaded', async () => {
    setup('/payouts', { [`GET ${PAYOUTS}`]: () => apiError(503, 'SERVICE_UNAVAILABLE') })

    expect(await screen.findByRole('button', { name: /Qayta urinish/ })).toBeInTheDocument()
  })
})
