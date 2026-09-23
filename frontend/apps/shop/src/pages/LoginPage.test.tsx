import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiError, json, renderWithApi, type Route } from '../test/renderApp'
import { LoginPage } from './LoginPage'

const user = { id: 'u1', phone: '+998901234567', full_name: 'Aziza', role: 'customer' }

const routes = [
  { path: '/login', element: <LoginPage /> },
  { path: '/', element: <p>Bosh sahifa</p> },
  { path: '/p/:slug', element: <p>Mahsulot sahifasi</p> },
]

function setup(api: Record<string, Route> = {}, entry = '/login?next=%2Fp%2Fchoynak') {
  const handlers: Record<string, Route> = {
    'POST /api/auth/otp/send/': () => new Response(null, { status: 204 }),
    'POST /api/auth/otp/verify/': (body) =>
      (body as { code: string }).code === '123456'
        ? json(200, { access: 'a1', refresh: 'r1', user })
        : apiError(400, 'OTP_INVALID'),
    ...api,
  }
  return renderWithApi(routes, handlers, entry)
}

const cells = () => screen.getAllByRole('textbox', { name: /-raqam, jami 6/ })

async function submitPhone(u: ReturnType<typeof userEvent.setup>, digits = '901234567') {
  const input = await screen.findByLabelText('Telefon raqam')
  await u.type(input, digits)
  await u.click(screen.getByRole('button', { name: 'Kod olish' }))
}

afterEach(() => vi.useRealTimers())

describe('LoginPage', () => {
  it('validates the phone before calling the API', async () => {
    const u = userEvent.setup()
    const { fetchMock } = setup()
    await u.click(await screen.findByRole('button', { name: 'Kod olish' }))
    expect(await screen.findByText('Telefon raqamni kiriting')).toBeInTheDocument()
    await u.type(screen.getByLabelText('Telefon raqam'), '9012')
    await u.click(screen.getByRole('button', { name: 'Kod olish' }))
    expect(await screen.findByText(/9 ta raqamdan/)).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('masks the phone, sends the code, maps a wrong code, then logs in and redirects back', async () => {
    const u = userEvent.setup()
    const { fetchMock, router } = setup()
    const input = await screen.findByLabelText('Telefon raqam')
    await u.type(input, '+998901234567')
    expect(input).toHaveValue('90 123 45 67')
    await u.click(screen.getByRole('button', { name: 'Kod olish' }))

    expect(await screen.findByRole('heading', { name: 'SMS kodni kiriting' })).toBeInTheDocument()
    const sendCall = fetchMock.mock.calls[0]!
    expect(JSON.parse(String(sendCall[1]!.body))).toEqual({ phone: '+998901234567' })
    expect(screen.getByText(/\+998 90 123 45 67/)).toBeInTheDocument()
    expect(screen.getByText('Kodni qayta yuborish: 01:00')).toBeInTheDocument()

    // wrong code: auto-submits on the 6th digit and shows the mapped message
    await u.click(cells()[0]!)
    await u.keyboard('111111')
    expect(await screen.findByText(/Kod noto'g'ri/)).toBeInTheDocument()
    await waitFor(() => expect(cells()[0]).toHaveValue(''))

    await u.click(cells()[0]!)
    await u.keyboard('123456')
    await waitFor(() => expect(router.state.location.pathname).toBe('/p/choynak'))
    expect(await screen.findByText('Xush kelibsiz!')).toBeInTheDocument()
  })

  it.each([
    ['OTP_EXPIRED', /muddati tugadi/],
    ['OTP_BLOCKED', /vaqtincha bloklandi/],
  ])('shows %s from verify', async (code, message) => {
    const u = userEvent.setup()
    setup({ 'POST /api/auth/otp/verify/': () => apiError(400, code) })
    await submitPhone(u)
    await u.click((await screen.findAllByRole('textbox', { name: /-raqam/ }))[0]!)
    await u.keyboard('654321')
    expect(await screen.findByText(message)).toBeInTheDocument()
    if (code === 'OTP_BLOCKED') {
      expect(cells()[0]).toBeDisabled()
      expect(screen.getByRole('button', { name: 'Tasdiqlash' })).toBeDisabled()
    } else {
      // an expired code can be replaced at once, without waiting for the timer
      expect(screen.getByRole('button', { name: 'Kodni qayta yuborish' })).toBeEnabled()
    }
  })

  it('shows phone errors from the API on the field or as a form error', async () => {
    const u = userEvent.setup()
    setup({ 'POST /api/auth/otp/send/': () => apiError(400, 'INVALID_PHONE') })
    await submitPhone(u)
    const input = screen.getByLabelText('Telefon raqam')
    await waitFor(() => expect(input).toHaveAccessibleDescription(/qabul qilinmadi/))
  })

  it('maps rate limiting on send', async () => {
    const u = userEvent.setup()
    setup({ 'POST /api/auth/otp/send/': () => apiError(429, 'OTP_RATE_LIMITED') })
    await submitPhone(u)
    expect(await screen.findByRole('alert')).toHaveTextContent(/juda tez-tez/)
  })

  it('unlocks resend after 60 seconds and sends a new code', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const u = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    const { fetchMock } = setup()
    await submitPhone(u)
    expect(await screen.findByText('Kodni qayta yuborish: 01:00')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Kodni qayta yuborish' })).not.toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(61_000))
    await u.click(await screen.findByRole('button', { name: 'Kodni qayta yuborish' }))
    expect(await screen.findByText('Yangi kod yuborildi')).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/otp/send/'))).toHaveLength(
      2,
    )
    expect(screen.getByText(/Kodni qayta yuborish: 0[01]:/)).toBeInTheDocument()
  })

  it('lets the user go back and change the number', async () => {
    const u = userEvent.setup()
    setup()
    await submitPhone(u)
    await u.click(await screen.findByRole('button', { name: "Raqamni o'zgartirish" }))
    expect(await screen.findByLabelText('Telefon raqam')).toBeInTheDocument()
  })
})
