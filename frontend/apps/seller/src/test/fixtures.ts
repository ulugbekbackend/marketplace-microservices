import type {
  Attribute,
  Category,
  SellerApplication,
  SellerProduct,
  SellerProductDetail,
  SellerVariant,
  User,
} from '@bozorcha/api-client'
import { json, type Route } from './renderApp'

export const sellerUser: User = {
  id: 'u1',
  phone: '+998901234567',
  full_name: 'Dilnoza',
  role: 'seller',
  date_joined: '2026-09-01T00:00:00Z',
}
export const customerUser: User = { ...sellerUser, role: 'customer' }

export const application = (patch: Partial<SellerApplication> = {}): SellerApplication => ({
  id: 'a1',
  shop_name: "Marg'ilon atlas",
  inn: '123456789',
  description: '',
  status: 'approved',
  reviewed_at: '2026-09-02T09:00:00Z',
  created_at: '2026-09-01T09:00:00Z',
  ...patch,
})

export const attributes: Attribute[] = [
  {
    id: 'color',
    code: 'color',
    name: 'Rang',
    values: [
      { id: 'red', value: 'Qizil' },
      { id: 'blue', value: "Ko'k" },
    ],
  },
  {
    id: 'size',
    code: 'size',
    name: "O'lcham",
    values: [
      { id: 's', value: 'S' },
      { id: 'm', value: 'M' },
    ],
  },
]

export const categories: Category[] = [
  {
    id: 'c-kiyim',
    name: 'Kiyim',
    slug: 'kiyim',
    children: [{ id: 'c-ayollar', name: 'Ayollar kiyimi', slug: 'ayollar', children: [] }],
  },
]

export const variant = (patch: Partial<SellerVariant> = {}): SellerVariant => ({
  id: 'v1',
  sku: 'ATLAS-QIZIL',
  price_tiyin: 45_000_000,
  stock: 10,
  reserved: 2,
  available: 8,
  is_active: true,
  attributes: [{ value_id: 'red', value: 'Qizil', code: 'color', name: 'Rang' }],
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  ...patch,
})

export const productDetail = (patch: Partial<SellerProductDetail> = {}): SellerProductDetail => ({
  id: 'p1',
  slug: 'atlas-koylak',
  title: "Atlas ko'ylak",
  status: 'active',
  category: { id: 'c-ayollar', name: 'Ayollar kiyimi', slug: 'ayollar' },
  min_price_tiyin: 45_000_000,
  max_price_tiyin: 45_000_000,
  in_stock: true,
  variants_count: 1,
  image_url: null,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  description: "Qo'lda tikilgan",
  variants: [variant()],
  images: [],
  ...patch,
})

export const listItem = (detail: SellerProductDetail): SellerProduct => {
  const { variants: _variants, images: _images, description: _description, ...item } = detail
  return item
}

/** Endpoints every panel page needs: the seller, their shop name, and fresh tokens. */
export const panelApi: Record<string, Route> = {
  'GET /api/auth/me/': () => json(200, sellerUser),
  'GET /api/auth/seller/application/': () => json(200, application()),
  'POST /api/auth/token/refresh/': () => json(200, { access: 'a2', refresh: 'r2' }),
  'GET /api/catalog/attributes/': () => json(200, attributes),
  'GET /api/catalog/categories/': () => json(200, categories),
}
