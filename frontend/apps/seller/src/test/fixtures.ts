import type {
  Attribute,
  Category,
  SellerApplication,
  SellerDailyStats,
  SellerPeriodStats,
  SellerStats,
  SellerSubOrder,
  SellerSubOrderDetail,
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
  stock_total: 10,
  reserved_total: 2,
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
  'GET /api/orders/seller/stats/': () => json(200, sellerStats()),
  'GET /api/orders/seller/': () => json(200, { items: [], total: 0, page: 1, page_size: 20 }),
}

/* ------------------------------------------------------------------ orders */

export const period = (orders = 0, gross = 0): SellerPeriodStats => ({
  orders,
  gross_tiyin: gross,
  net_tiyin: Math.round(gross * 0.9),
})

/** 30 days ending 2026-09-27; `sales` maps a day of month to [orders, gross tiyin]. */
export const dailyStats = (sales: Record<number, [number, number]> = {}): SellerDailyStats[] =>
  Array.from({ length: 30 }, (_, i) => {
    const date = new Date(Date.UTC(2026, 7, 29 + i)).toISOString().slice(0, 10)
    const [orders, gross] = sales[Number(date.slice(8))] ?? [0, 0]
    return { date, ...period(orders, gross) }
  })

export const sellerStats = (patch: Partial<SellerStats> = {}): SellerStats => ({
  today: period(2, 90_000_000),
  week: period(5, 225_000_000),
  month: period(12, 525_000_000),
  daily: dailyStats({ 26: [3, 135_000_000], 27: [2, 90_000_000] }),
  by_status: { NEW: 3, ACCEPTED: 2, SHIPPED: 1, DELIVERED: 4, CANCELLED_BY_SELLER: 1 },
  ...patch,
})

export const emptyStats = (): SellerStats => ({
  today: period(),
  week: period(),
  month: period(),
  daily: dailyStats(),
  by_status: { NEW: 0, ACCEPTED: 0, SHIPPED: 0, DELIVERED: 0, CANCELLED_BY_SELLER: 0 },
})

export const subOrder = (patch: Partial<SellerSubOrder> = {}): SellerSubOrder => ({
  id: 's1',
  order_id: 'a1b2c3d4-0000-4000-8000-000000000001',
  status: 'NEW',
  subtotal_tiyin: 90_000_000,
  commission_tiyin: 9_000_000,
  net_tiyin: 81_000_000,
  items_count: 2,
  created_at: '2026-09-27T09:00:00Z',
  updated_at: '2026-09-27T09:00:00Z',
  customer_name: 'Aziza Karimova',
  city: 'Toshkent',
  ...patch,
})

export const subOrderDetail = (
  patch: Partial<SellerSubOrderDetail> = {},
): SellerSubOrderDetail => ({
  ...subOrder(),
  commission_rate: '0.1000',
  tracking_number: '',
  cancel_reason: '',
  items: [
    {
      id: 'i1',
      variant_id: 'v1',
      title: "Atlas ko'ylak (Qizil)",
      sku: 'ATLAS-QIZIL',
      image: 'https://img.test/atlas.webp',
      price_tiyin: 45_000_000,
      qty: 2,
      line_total_tiyin: 90_000_000,
    },
  ],
  delivery_address: {
    full_name: 'Aziza Karimova',
    phone: '+998901112233',
    region: 'Toshkent shahri',
    city: 'Toshkent',
    street: 'Navoiy 12',
    notes: 'Kechqurun',
  },
  order_status: 'PAID',
  history: [
    { from_status: null, to_status: 'NEW', reason: '', created_at: '2026-09-27T09:00:00Z' },
  ],
  ...patch,
})
