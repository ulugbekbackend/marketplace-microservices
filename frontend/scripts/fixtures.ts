// Mock catalog data for screenshots (route interception): realistic Uzbek listings.
export const IMAGE_HOST = 'https://img.fixture.test'

type Palette = { bg: string; shape: string; accent: string }
const palettes: Palette[] = [
  { bg: '#E9E2D6', shape: '#1F5F8B', accent: '#D8A23B' },
  { bg: '#E3EDE7', shape: '#2F6F5E', accent: '#F1C27D' },
  { bg: '#F1E4DC', shape: '#A34A3A', accent: '#F4D8B8' },
  { bg: '#E6E4EE', shape: '#433A63', accent: '#C9B8F0' },
  { bg: '#EDE9DF', shape: '#6B5B3E', accent: '#E0C68C' },
  { bg: '#E0EAF0', shape: '#1E3A4C', accent: '#8FB8D0' },
]

/** A flat product "photo": soft background, floor shadow, one object shape per index. */
export function productSvg(index: number, size = 800): string {
  const p = palettes[index % palettes.length]!
  const s = size
  const shapes = [
    `<rect x="${s * 0.28}" y="${s * 0.2}" width="${s * 0.44}" height="${s * 0.56}" rx="${s * 0.05}" fill="${p.shape}"/><rect x="${s * 0.28}" y="${s * 0.2}" width="${s * 0.44}" height="${s * 0.12}" rx="${s * 0.05}" fill="${p.accent}"/>`,
    `<ellipse cx="${s / 2}" cy="${s * 0.5}" rx="${s * 0.26}" ry="${s * 0.22}" fill="${p.shape}"/><rect x="${s * 0.42}" y="${s * 0.22}" width="${s * 0.16}" height="${s * 0.08}" rx="${s * 0.03}" fill="${p.accent}"/>`,
    `<rect x="${s * 0.34}" y="${s * 0.14}" width="${s * 0.32}" height="${s * 0.64}" rx="${s * 0.06}" fill="${p.shape}"/><rect x="${s * 0.37}" y="${s * 0.19}" width="${s * 0.26}" height="${s * 0.5}" rx="${s * 0.02}" fill="${p.accent}"/>`,
    `<path d="M ${s * 0.25} ${s * 0.3} L ${s * 0.4} ${s * 0.2} L ${s * 0.6} ${s * 0.2} L ${s * 0.75} ${s * 0.3} L ${s * 0.68} ${s * 0.4} L ${s * 0.64} ${s * 0.36} L ${s * 0.64} ${s * 0.76} L ${s * 0.36} ${s * 0.76} L ${s * 0.36} ${s * 0.36} L ${s * 0.32} ${s * 0.4} Z" fill="${p.shape}"/><rect x="${s * 0.36}" y="${s * 0.5}" width="${s * 0.28}" height="${s * 0.05}" fill="${p.accent}"/>`,
    `<circle cx="${s / 2}" cy="${s * 0.48}" r="${s * 0.26}" fill="${p.shape}"/><circle cx="${s / 2}" cy="${s * 0.48}" r="${s * 0.16}" fill="${p.accent}"/><circle cx="${s / 2}" cy="${s * 0.48}" r="${s * 0.07}" fill="${p.shape}"/>`,
    `<rect x="${s * 0.2}" y="${s * 0.34}" width="${s * 0.6}" height="${s * 0.34}" rx="${s * 0.04}" fill="${p.shape}"/><rect x="${s * 0.26}" y="${s * 0.4}" width="${s * 0.48}" height="${s * 0.22}" rx="${s * 0.02}" fill="none" stroke="${p.accent}" stroke-width="${s * 0.015}"/>`,
  ]
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${s}" height="${s}" viewBox="0 0 ${s} ${s}"><rect width="${s}" height="${s}" fill="${p.bg}"/><ellipse cx="${s / 2}" cy="${s * 0.8}" rx="${s * 0.3}" ry="${s * 0.04}" fill="#000" opacity=".12"/>${shapes[index % shapes.length]}</svg>`
}

const img = (i: number) => `${IMAGE_HOST}/p/${i}.svg`

export const categories = [
  {
    id: 'c-kiyim',
    name: 'Kiyim va poyabzal',
    slug: 'kiyim',
    children: [
      { id: 'c-ayollar', name: 'Ayollar kiyimi', slug: 'ayollar-kiyimi', children: [] },
      { id: 'c-erkaklar', name: 'Erkaklar kiyimi', slug: 'erkaklar-kiyimi', children: [] },
      { id: 'c-poyabzal', name: 'Poyabzal', slug: 'poyabzal', children: [] },
    ],
  },
  {
    id: 'c-elektronika',
    name: 'Elektronika',
    slug: 'elektronika',
    children: [
      { id: 'c-telefon', name: 'Smartfonlar', slug: 'smartfonlar-telefon', children: [] },
      { id: 'c-quloqchin', name: 'Quloqchinlar', slug: 'quloqchinlar', children: [] },
    ],
  },
  {
    id: 'c-uy',
    name: "Uy-ro'zg'or",
    slug: 'uy-rozgor',
    children: [
      { id: 'c-idish', name: 'Oshxona idishlari', slug: 'oshxona-idish', children: [] },
      { id: 'c-gilam', name: 'Gilam va palaslar', slug: 'gilam', children: [] },
      { id: 'c-tekstil', name: 'Uy tekstili', slug: 'uy-tekstili', children: [] },
    ],
  },
  { id: 'c-gozallik', name: "Go'zallik", slug: 'gozallik', children: [] },
  {
    id: 'c-bolalar',
    name: 'Bolalar uchun',
    slug: 'bolalar',
    children: [{ id: 'c-oyinchoq', name: "O'yinchoqlar", slug: 'oyinchoqlar', children: [] }],
  },
  { id: 'c-sport', name: 'Sport va dam olish', slug: 'sport', children: [] },
  { id: 'c-kitob', name: 'Kitoblar', slug: 'kitoblar', children: [] },
  { id: 'c-oziq', name: 'Oziq-ovqat', slug: 'oziq-ovqat', children: [] },
]

const sellers = {
  atlas: { id: 's1', shop_name: "Marg'ilon atlas", slug: 'margilon-atlas', is_verified: true },
  rishton: { id: 's2', shop_name: 'Rishton sopol ustaxonasi', slug: 'rishton-sopol' },
  tech: { id: 's3', shop_name: 'Chilonzor Texno', slug: 'chilonzor-texno' },
  bolajon: { id: 's4', shop_name: 'Bolajon', slug: 'bolajon' },
}

const so = (som: number) => som * 100

export const products = [
  ["Atlas ko'ylak, qo'lda tikilgan", 'atlas-koylak', 420_000, 560_000, true, sellers.atlas],
  ["Rishton lagani, 32 sm, ko'k naqsh", 'rishton-lagan', 185_000, 185_000, true, sellers.rishton],
  ['Samsung Galaxy A55 8/256 GB', 'galaxy-a55', 5_290_000, 5_690_000, true, sellers.tech],
  ["Paxta sochiq to'plami, 3 dona", 'paxta-sochiq', 129_000, 129_000, true, sellers.atlas],
  [
    "Simsiz quloqchin, shovqin so'ndirish bilan",
    'simsiz-quloqchin',
    649_000,
    649_000,
    false,
    sellers.tech,
  ],
  ['Adras yostiq jildi 50x70', 'adras-yostiq', 95_000, 110_000, true, sellers.atlas],
  ["Choynak va 6 piyola to'plami", 'choynak-toplam', 340_000, 340_000, true, sellers.rishton],
  ['Bolalar qishki kurtkasi, 4-10 yosh', 'bolalar-kurtka', 389_000, 459_000, true, sellers.bolajon],
  ["Charm hamyon, qo'lda ishlangan", 'charm-hamyon', 210_000, 210_000, true, sellers.atlas],
  ["Yog'och konstruktor, 120 detal", 'yogoch-konstruktor', 175_000, 175_000, true, sellers.bolajon],
  ['Aqlli soat, AMOLED ekran', 'aqlli-soat', 1_150_000, 1_150_000, true, sellers.tech],
  ['Kulolchilik kosasi, 4 dona', 'kulol-kosa', 160_000, 160_000, false, sellers.rishton],
].map(([title, slug, min, max, inStock, seller], i) => ({
  id: `p${i + 1}`,
  title: title as string,
  slug: slug as string,
  min_price_tiyin: so(min as number),
  max_price_tiyin: so(max as number),
  in_stock: inStock as boolean,
  image_url: img(i),
  category: { id: 'c-kiyim', name: 'Kiyim va poyabzal', slug: 'kiyim' },
  created_at: '2026-09-01T08:00:00Z',
  seller: seller as (typeof sellers)['atlas'],
}))

/** The products as search hits (`GET /api/search` items). */
export const searchItems = products.map((p, i) => ({
  id: p.id,
  slug: p.slug,
  title: p.title,
  seller_id: p.seller.id,
  shop_name: p.seller.shop_name,
  min_price: p.min_price_tiyin,
  max_price: p.max_price_tiyin,
  in_stock: p.in_stock,
  image_url: p.image_url,
  rating: i % 3 === 0 ? 4.8 : 0,
}))

/** Facets as the search service returns them (counts are illustrative). */
export function searchFacets(selectedColors: string[] = []) {
  const value = (v: string, count: number) => ({
    value: v,
    count,
    selected: selectedColors.includes(v),
  })
  return {
    categories: [
      { id: 'c-kiyim', name: 'Kiyim va poyabzal', count: 64 },
      { id: 'c-ayollar', name: 'Ayollar kiyimi', count: 31 },
      { id: 'c-erkaklar', name: 'Erkaklar kiyimi', count: 21 },
      { id: 'c-poyabzal', name: 'Poyabzal', count: 12 },
      { id: 'c-uy', name: "Uy-ro'zg'or", count: 40 },
      { id: 'c-tekstil', name: 'Uy tekstili', count: 18 },
      { id: 'c-elektronika', name: 'Elektronika', count: 52 },
      { id: 'c-bolalar', name: 'Bolalar uchun', count: 16 },
    ],
    price_ranges: [
      { key: 'lt_100k', from_tiyin: null, to_tiyin: so(100_000), count: 9 },
      { key: '100k_500k', from_tiyin: so(100_000), to_tiyin: so(500_000), count: 61 },
      { key: '500k_1m', from_tiyin: so(500_000), to_tiyin: so(1_000_000), count: 26 },
      { key: '1m_5m', from_tiyin: so(1_000_000), to_tiyin: so(5_000_000), count: 14 },
      { key: 'gte_5m', from_tiyin: so(5_000_000), to_tiyin: null, count: 0 },
    ],
    attributes: [
      {
        code: 'color',
        values: [
          value('qizil', 18),
          value("ko'k", 15),
          value('oq', 12),
          value('qora', 9),
          value('yashil', 6),
          value('kulrang', 4),
          value('sariq', 2),
        ],
      },
      { code: 'size', values: [value('S', 20), value('M', 24), value('L', 17), value('XL', 8)] },
    ],
  }
}

const variant = (
  id: string,
  sku: string,
  som: number,
  available: number,
  color: string,
  size: string,
) => ({
  id,
  sku,
  price_tiyin: so(som),
  available,
  in_stock: available > 0,
  attributes: [
    { code: 'color', name: 'Rang', value: color, value_id: `color-${color}` },
    { code: 'size', name: "O'lcham", value: size, value_id: `size-${size}` },
  ],
})

export const productDetail = {
  id: 'p1',
  title: "Atlas ko'ylak, qo'lda tikilgan",
  slug: 'atlas-koylak',
  description:
    "Marg'ilon ustalari to'qigan tabiiy ipak atlasdan tikilgan ko'ylak. Yengil, havo o'tkazadi, yozgi to'y va bayramlar uchun mos.\n\nTarkibi: 100% ipak. Faqat qo'lda, sovuq suvda yuving.",
  category: { id: 'c-ayollar', name: 'Ayollar kiyimi', slug: 'ayollar-kiyimi' },
  breadcrumbs: [
    { id: 'c-kiyim', name: 'Kiyim va poyabzal', slug: 'kiyim' },
    { id: 'c-ayollar', name: 'Ayollar kiyimi', slug: 'ayollar-kiyimi' },
  ],
  image_url: img(0),
  created_at: '2026-09-01T08:00:00Z',
  updated_at: '2026-09-20T08:00:00Z',
  seller: sellers.atlas,
  images: [0, 3, 5, 8].map((n, position) => ({
    id: `img${position}`,
    thumb_url: img(n),
    medium_url: img(n),
    large_url: img(n),
    position,
  })),
  variants: [
    variant('v1', 'ATL-KOK-S', 420_000, 4, "Ko'k", 'S'),
    variant('v2', 'ATL-KOK-M', 420_000, 9, "Ko'k", 'M'),
    variant('v3', 'ATL-KOK-L', 460_000, 0, "Ko'k", 'L'),
    variant('v4', 'ATL-QIZIL-M', 480_000, 6, 'Qizil', 'M'),
    variant('v5', 'ATL-QIZIL-L', 560_000, 2, 'Qizil', 'L'),
    variant('v6', 'ATL-YASHIL-S', 420_000, 0, 'Yashil', 'S'),
  ],
  min_price_tiyin: so(420_000),
  max_price_tiyin: so(560_000),
  in_stock: true,
}

export const shop = {
  id: 's1',
  shop_name: "Marg'ilon atlas",
  slug: 'margilon-atlas',
  product_count: 48,
  is_verified: true,
  created_at: '2024-04-12T08:00:00Z',
}

const cartLine = (
  variantId: string,
  product: (typeof products)[number],
  som: number,
  qty: number,
  availableQty: number,
  attributes: [string, string][],
  previousSom: number | null = null,
) => {
  const available = availableQty >= qty
  return {
    variant_id: variantId,
    product_id: product.id,
    product_slug: product.slug,
    title: product.title,
    sku: `SKU-${variantId}`,
    image_url: product.image_url,
    attributes: attributes.map(([name, value]) => ({ code: name.toLowerCase(), name, value })),
    qty,
    price_tiyin: so(som),
    line_total_tiyin: so(som) * qty,
    available_qty: availableQty,
    available,
    price_changed: previousSom !== null,
    previous_price_tiyin: previousSom === null ? null : so(previousSom),
  }
}

const byId = (id: string) => products.find((p) => p.id === id)!

const cartGroups = [
  {
    seller_id: sellers.atlas.id,
    shop_name: sellers.atlas.shop_name,
    items: [
      cartLine('v1', byId('p1'), 420_000, 1, 4, [
        ['Rang', "Ko'k"],
        ["O'lcham", 'S'],
      ]),
      cartLine('v20', byId('p6'), 110_000, 2, 12, [['Rang', 'Qizil']], 95_000),
    ],
  },
  {
    seller_id: sellers.rishton.id,
    shop_name: sellers.rishton.shop_name,
    items: [
      cartLine('v30', byId('p7'), 340_000, 1, 5, []),
      cartLine('v31', byId('p12'), 160_000, 2, 0, [['Rang', 'Firuza']]),
    ],
  },
].map((group) => ({
  ...group,
  subtotal_tiyin: group.items
    .filter((i) => i.available)
    .reduce((sum, i) => sum + i.line_total_tiyin, 0),
}))

export const cart = {
  groups: cartGroups,
  total_tiyin: cartGroups.reduce((sum, g) => sum + g.subtotal_tiyin, 0),
  items_count: cartGroups.flatMap((g) => g.items).reduce((sum, i) => sum + i.qty, 0),
  has_unavailable: true,
  has_price_changes: true,
  removed: ['v-gone'],
}

/** The same cart with only sellable lines: what checkout sees after the customer fixed it. */
export const cleanCart = (() => {
  const groups = cartGroups
    .map((group) => ({ ...group, items: group.items.filter((i) => i.available) }))
    .filter((group) => group.items.length > 0)
  return {
    groups,
    total_tiyin: groups.reduce((sum, g) => sum + g.subtotal_tiyin, 0),
    items_count: groups.flatMap((g) => g.items).reduce((sum, i) => sum + i.qty, 0),
    has_unavailable: false,
    has_price_changes: false,
    removed: [],
  }
})()

export const customer = {
  id: 'u1',
  phone: '+998901112233',
  full_name: 'Aziza Karimova',
  role: 'customer',
}

export const ORDER_ID = '7f3c9a21-5b8e-4c1d-9f20-6a4e1b7d3c55'

/** A reserved order whose payment window ends `minutesLeft` from now. */
export function reservedOrder(minutesLeft = 11.5) {
  const now = Date.now()
  const at = (offsetMs: number) => new Date(now + offsetMs).toISOString()
  return {
    id: ORDER_ID,
    status: 'RESERVED',
    reserved_until: at(minutesLeft * 60_000),
    late_payment: false,
    total_tiyin: cleanCart.total_tiyin,
    cancel_reason: '',
    created_at: at(-3.5 * 60_000),
    updated_at: at(-3.4 * 60_000),
    delivery_address: {
      full_name: customer.full_name,
      phone: customer.phone,
      region: "Farg'ona viloyati",
      city: "Marg'ilon",
      street: "Mustaqillik ko'chasi, 14-uy",
      notes: "Darvoza ko'k rangda, qo'ng'iroq qiling",
    },
    history: [
      { from_status: null, to_status: 'PENDING', reason: '', created_at: at(-3.5 * 60_000) },
      { from_status: 'PENDING', to_status: 'RESERVED', reason: '', created_at: at(-3.4 * 60_000) },
    ],
    sellers: cleanCart.groups.map((group) => ({
      seller_id: group.seller_id,
      shop_name: group.shop_name,
      sub_order_id: null,
      cancel_reason: null,
      tracking_number: null,
      history: [],
      status: null,
      subtotal_tiyin: group.subtotal_tiyin,
      items: group.items.map((item, i) => ({
        id: `${item.variant_id}-${i}`,
        variant_id: item.variant_id,
        title: item.title,
        sku: item.sku,
        image_url: item.image_url,
        qty: item.qty,
        price_tiyin: item.price_tiyin,
        line_total_tiyin: item.line_total_tiyin,
      })),
    })),
  }
}

const orderSummary = (id: string, status: string, som: number, count: number, daysAgo: number) => ({
  id,
  status,
  total_tiyin: so(som),
  items_count: count,
  reserved_until: null,
  created_at: new Date(Date.UTC(2026, 8, 27 - daysAgo, 9 + daysAgo, 15)).toISOString(),
})

export const orderList = [
  { ...orderSummary(ORDER_ID, 'RESERVED', 980_000, 4, 0) },
  orderSummary('2a9e4c10-1111-4000-8000-000000000001', 'PAID', 185_000, 1, 1),
  orderSummary('b41d0e77-2222-4000-8000-000000000002', 'COMPLETED', 5_290_000, 1, 6),
  orderSummary('c9f2a5e3-3333-4000-8000-000000000003', 'EXPIRED', 340_000, 2, 9),
  orderSummary('d03b7f88-4444-4000-8000-000000000004', 'CANCELLED', 129_000, 3, 14),
]
