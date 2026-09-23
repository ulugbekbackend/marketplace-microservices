import type { ProductDetail } from '@bozorcha/api-client'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { apiError, json, renderWithApi } from '../test/renderApp'
import { ProductPage } from './ProductPage'

const attrs = (color: string, size: string) => [
  { code: 'color', name: 'Rang', value: color, value_id: `color-${color}` },
  { code: 'size', name: "O'lcham", value: size, value_id: `size-${size}` },
]

const product: ProductDetail = {
  id: 'p1',
  title: "Paxta ko'ylak",
  slug: 'paxta-koylak',
  description: 'Yengil paxta mato.',
  category: { id: 'c2', name: 'Ayollar kiyimi', slug: 'ayollar-kiyimi' },
  breadcrumbs: [
    { id: 'c1', name: 'Kiyim', slug: 'kiyim' },
    { id: 'c2', name: 'Ayollar kiyimi', slug: 'ayollar-kiyimi' },
  ],
  seller: { id: 's1', shop_name: "Marg'ilon atlas", slug: 'margilon-atlas', is_verified: true },
  image_url: null,
  images: [],
  created_at: '2026-09-01T08:00:00Z',
  updated_at: '2026-09-20T08:00:00Z',
  variants: [
    {
      id: 'v1',
      sku: 'K-QS',
      price_tiyin: 150_000_00,
      available: 3,
      in_stock: true,
      attributes: attrs('Qora', 'S'),
    },
    {
      id: 'v2',
      sku: 'K-OM',
      price_tiyin: 165_000_00,
      available: 12,
      in_stock: true,
      attributes: attrs('Oq', 'M'),
    },
    {
      id: 'v3',
      sku: 'K-YS',
      price_tiyin: 150_000_00,
      available: 0,
      in_stock: false,
      attributes: attrs('Yashil', 'S'),
    },
  ],
  min_price_tiyin: 150_000_00,
  max_price_tiyin: 165_000_00,
  in_stock: true,
}

const routes = [{ path: '/p/:slug', element: <ProductPage /> }]
const plain = (text: string | null) => (text ?? '').replaceAll(String.fromCharCode(0xa0), ' ')

function setup(overrides: Record<string, () => Response> = {}) {
  return renderWithApi(
    routes,
    {
      'GET /api/catalog/products/paxta-koylak/': () => json(200, product),
      'GET /api/catalog/shops/margilon-atlas/': () =>
        json(200, {
          id: 's1',
          shop_name: "Marg'ilon atlas",
          slug: 'margilon-atlas',
          product_count: 42,
          created_at: '2024-03-01T00:00:00Z',
        }),
      ...overrides,
    },
    '/p/paxta-koylak',
  )
}

describe('ProductPage', () => {
  it('updates price and stock when switching variants; sold-out values are disabled', async () => {
    const u = userEvent.setup()
    setup()
    expect(
      await screen.findByRole('heading', { level: 1, name: "Paxta ko'ylak" }),
    ).toBeInTheDocument()
    // cheapest in-stock variant preselected
    expect(plain(screen.getByTestId('price').textContent)).toBe("150 000 so'm")
    expect(screen.getByText('Faqat 3 ta qoldi')).toBeInTheDocument()

    const colors = screen.getByRole('group', { name: /Rang/ })
    expect(within(colors).getByRole('radio', { name: 'Qora' })).toBeChecked()
    expect(within(colors).getByRole('radio', { name: /Yashil/ })).toBeDisabled()

    // Oq only exists in M: choosing it moves the size too
    await u.click(within(colors).getByText('Oq'))
    expect(plain(screen.getByTestId('price').textContent)).toBe("165 000 so'm")
    expect(screen.getByText('Omborda: 12 ta')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'M' })).toBeChecked()
    expect(screen.getByText('Artikul: K-OM')).toBeInTheDocument()
  })

  it('keeps "Savatchaga" disabled and explains why', async () => {
    const u = userEvent.setup()
    setup()
    const button = await screen.findByRole('button', { name: 'Savatchaga' })
    expect(button).toHaveAttribute('aria-disabled', 'true')
    await u.click(button)
    expect(
      await screen.findByText('Savatcha tez orada ishga tushadi', { selector: 'p.font-semibold' }),
    ).toBeInTheDocument()
  })

  it('links the shop card to the shop page', async () => {
    setup()
    const link = await screen.findByRole('link', { name: /Marg'ilon atlas/ })
    expect(link).toHaveAttribute('href', '/shop/margilon-atlas')
    expect(await within(link).findByText('42 ta mahsulot')).toBeInTheDocument()
  })

  it('shows not found for a 404 and a retryable error otherwise', async () => {
    setup({ 'GET /api/catalog/products/paxta-koylak/': () => apiError(404, 'NOT_FOUND') })
    expect(await screen.findByRole('heading', { name: 'Mahsulot topilmadi' })).toBeInTheDocument()
  })

  it('offers retry on server errors', async () => {
    const u = userEvent.setup()
    let calls = 0
    setup({
      'GET /api/catalog/products/paxta-koylak/': () =>
        ++calls === 1 ? apiError(500, 'BOOM') : json(200, product),
    })
    await u.click(await screen.findByRole('button', { name: 'Qayta urinish' }))
    expect(
      await screen.findByRole('heading', { level: 1, name: "Paxta ko'ylak" }),
    ).toBeInTheDocument()
  })

  it('shows the full category path from breadcrumbs', async () => {
    setup()
    const trail = await screen.findByRole('navigation', { name: "Sahifa yo'li" })
    expect(within(trail).getByRole('link', { name: 'Kiyim' })).toHaveAttribute(
      'href',
      '/catalog/kiyim',
    )
    expect(within(trail).getByRole('link', { name: 'Ayollar kiyimi' })).toHaveAttribute(
      'href',
      '/catalog/ayollar-kiyimi',
    )
    expect(within(trail).getByText("Paxta ko'ylak")).toHaveAttribute('aria-current', 'page')
  })

  it('limits the quantity to the available units and marks verified shops', async () => {
    const u = userEvent.setup()
    setup()
    const stepper = await screen.findByRole('spinbutton', { name: 'Soni' })
    expect(stepper).toHaveAttribute('aria-valuemax', '3')
    expect(screen.getByText("Ko'pi bilan 3 ta")).toBeInTheDocument()
    const increase = screen.getByRole('button', { name: "Ko'paytirish" })
    await u.click(increase)
    await u.click(increase)
    expect(stepper).toHaveValue('3')
    expect(increase).toBeDisabled()
    expect(screen.getAllByRole('img', { name: "Tasdiqlangan do'kon" }).length).toBeGreaterThan(0)
  })

  it('treats in_stock variants with no available units as sold out', async () => {
    const reserved = {
      ...product,
      variants: [{ ...product.variants[0]!, in_stock: true, available: 0 }],
    }
    setup({ 'GET /api/catalog/products/paxta-koylak/': () => json(200, reserved) })
    expect(await screen.findByText('Tugagan', { selector: 'p' })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: 'Soni' })).toBeDisabled()
  })

  it('handles products without prices and images that are still processing', async () => {
    const draft = {
      ...product,
      variants: [],
      min_price_tiyin: null,
      max_price_tiyin: null,
      images: [
        { id: 'i1', thumb_url: null, medium_url: null, large_url: null, position: 0 },
        { id: 'i2', thumb_url: 'https://img.test/t.jpg', medium_url: null, large_url: null },
      ],
    }
    setup({ 'GET /api/catalog/products/paxta-koylak/': () => json(200, draft) })
    expect(await screen.findByText('Narxi hali belgilanmagan')).toBeInTheDocument()
    const image = screen.getByRole('img', { name: /1-rasm/ })
    expect(image).toHaveAttribute('src', 'https://img.test/t.jpg')
    expect(image).not.toHaveAttribute('srcset')
  })
})
