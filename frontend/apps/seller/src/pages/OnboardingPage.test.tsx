import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { routes } from '../routes'
import { application, customerUser, panelApi, sellerUser } from '../test/fixtures'
import { apiError, json, renderWithApi, type Route } from '../test/renderApp'

function setup(api: Record<string, Route>, entry = '/', signedIn = true) {
  return renderWithApi(routes, { ...panelApi, ...api }, entry, { signedIn })
}

describe('role routing and onboarding', () => {
  it('sends guests to the login page', async () => {
    const { router } = setup({}, '/products', false)
    expect(
      await screen.findByRole('heading', { name: 'Sotuvchi kabinetiga kirish' }),
    ).toBeInTheDocument()
    expect(router.state.location.search).toBe('?next=%2Fproducts')
  })

  it('opens the panel for sellers and keeps them out of onboarding', async () => {
    const { router } = setup({}, '/onboarding')
    expect(await screen.findByRole('heading', { name: "Marg'ilon atlas" })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/')
    expect(screen.getAllByRole('navigation', { name: 'Kabinet menyusi' }).length).toBeGreaterThan(0)
  })

  it('shows a customer without an application the form, validates it and applies', async () => {
    const u = userEvent.setup()
    const { callsTo, router } = setup({
      'GET /api/auth/me/': () => json(200, customerUser),
      'GET /api/auth/seller/application/': () => apiError(404, 'NOT_FOUND'),
      'POST /api/auth/seller/apply/': (body) =>
        json(201, application({ ...(body as object), status: 'pending', reviewed_at: null })),
    })
    expect(
      await screen.findByRole('heading', { name: "Sotuvchi bo'lish uchun ariza" }),
    ).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/onboarding')

    await u.click(screen.getByRole('button', { name: 'Ariza yuborish' }))
    expect(await screen.findByText(/kamida 2 ta belgi/)).toBeInTheDocument()
    expect(screen.getByText("STIR 9 ta raqamdan iborat bo'lishi kerak")).toBeInTheDocument()
    expect(callsTo('POST', '/api/auth/seller/apply/')).toHaveLength(0)

    await u.type(screen.getByLabelText("Do'kon nomi"), 'Atlas uyi')
    await u.type(screen.getByLabelText('STIR (INN)'), '123456789')
    await u.click(screen.getByRole('button', { name: 'Ariza yuborish' }))

    expect(
      await screen.findByRole('heading', { name: "Ariza ko'rib chiqilmoqda" }),
    ).toBeInTheDocument()
    const [, init] = callsTo('POST', '/api/auth/seller/apply/')[0]!
    expect(JSON.parse(String(init!.body))).toEqual({
      shop_name: 'Atlas uyi',
      inn: '123456789',
      description: '',
    })
  })

  it('lets a rejected applicant apply again with the previous answers', async () => {
    const u = userEvent.setup()
    setup({
      'GET /api/auth/me/': () => json(200, customerUser),
      'GET /api/auth/seller/application/': () => json(200, application({ status: 'rejected' })),
    })
    expect(await screen.findByRole('heading', { name: 'Ariza rad etildi' })).toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: 'Qayta topshirish' }))
    expect(screen.getByLabelText("Do'kon nomi")).toHaveValue("Marg'ilon atlas")
    expect(screen.getByLabelText('STIR (INN)')).toHaveValue('123456789')
  })

  it('refreshes the tokens once approved and opens the panel', async () => {
    let role: 'customer' | 'seller' = 'customer'
    const { callsTo, router } = setup({
      'GET /api/auth/me/': () => json(200, { ...sellerUser, role }),
      'POST /api/auth/token/refresh/': () => {
        role = 'seller'
        return json(200, { access: 'a2', refresh: 'r2' })
      },
    })
    await waitFor(() => expect(router.state.location.pathname).toBe('/'))
    expect(await screen.findByRole('heading', { name: "Marg'ilon atlas" })).toBeInTheDocument()
    expect(callsTo('POST', '/api/auth/token/refresh/')).toHaveLength(1)
  })
})
