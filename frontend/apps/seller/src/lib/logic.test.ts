import { ApiError, CLIENT_ERROR, type Attribute, type SellerVariant } from '@bozorcha/api-client'
import { describe, expect, it } from 'vitest'
import { flattenCategories, indentedLabel } from './categories'
import { MAX_PRICE_TIYIN, normalizeSomInput, somToTiyin, tiyinToSomInput } from './money'
import { hasMatrixErrors, productSchema, validateMatrix } from './productForm'
import { productSaveError, reservedFromError, variantFailure } from './saveProduct'
import {
  BASE_KEY,
  cartesian,
  combinationKey,
  initialMatrix,
  lockedValueIds,
  refreshAutoSkus,
  skuBase,
  skuPart,
  suggestSku,
  syncRows,
  type VariantRow,
} from './variantMatrix'

const attributes: Attribute[] = [
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
      { id: 'l', value: 'L' },
    ],
  },
]

const variant = (id: string, values: [string, string][], extra: Partial<SellerVariant> = {}) =>
  ({
    id,
    sku: `SKU-${id}`,
    price_tiyin: 10_000_000,
    stock: 5,
    reserved: 0,
    available: 5,
    is_active: true,
    attributes: values.map(([value_id, value]) => ({ value_id, value, code: '', name: '' })),
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...extra,
  }) as SellerVariant

describe("so'm <-> tiyin", () => {
  it('parses so’m text into integer tiyin without floating point', () => {
    expect(somToTiyin('1 250 000')).toBe(125_000_000)
    expect(somToTiyin('1 250 000')).toBe(125_000_000)
    expect(somToTiyin('12500,5')).toBe(1_250_050)
    expect(somToTiyin('0.07')).toBe(7)
    expect(somToTiyin('19.99')).toBe(1999)
    expect(somToTiyin('0010')).toBe(1000)
    expect(Number.isInteger(somToTiyin('1.1'))).toBe(true)
  })

  it('rejects malformed input and absurd sizes', () => {
    for (const bad of ['', ' ', 'abc', '1.234', '-5', '1,2,3', '1e5', '12 so’m']) {
      expect(somToTiyin(bad)).toBeNull()
    }
    expect(somToTiyin('9999999999999')).toBeNull()
    expect(somToTiyin('100 000 000 000')).toBe(MAX_PRICE_TIYIN)
  })

  it('formats tiyin back for editing and normalises typed text', () => {
    expect(tiyinToSomInput(125_000_000)).toBe('1 250 000')
    expect(tiyinToSomInput(1_250_050)).toBe('12 500,50')
    expect(tiyinToSomInput(5)).toBe('0,05')
    expect(tiyinToSomInput(-1)).toBe('')
    expect(normalizeSomInput('125000')).toBe('125 000')
    expect(normalizeSomInput('abc')).toBe('abc')
  })
})

describe('variant matrix', () => {
  it('builds the cartesian product, including the empty and single-list cases', () => {
    expect(cartesian([])).toEqual([[]])
    expect(cartesian([['a', 'b']])).toEqual([['a'], ['b']])
    expect(
      cartesian<string | number>([
        ['a', 'b'],
        [1, 2, 3],
      ]),
    ).toHaveLength(6)
    expect(cartesian([['a'], []])).toEqual([])
    expect(cartesian([['a', 'b'], ['x']])).toEqual([
      ['a', 'x'],
      ['b', 'x'],
    ])
  })

  it('keys combinations independently of value order', () => {
    expect(combinationKey(['m', 'red'])).toBe(combinationKey(['red', 'm']))
    expect(combinationKey([])).toBe(BASE_KEY)
  })

  it('suggests valid, unique SKUs from Uzbek text', () => {
    expect(skuPart("Qo'ng'ir rang")).toBe('QONGIR-RANG')
    expect(skuPart('Oʻzbek  atlas!')).toBe('OZBEK-ATLAS')
    expect(skuBase("Atlas ko'ylak, qo'lda tikilgan")).toBe('ATLAS-KOYLAK-QOL')
    expect(skuBase('!!!')).toBe('SKU')
    expect(suggestSku('ATLAS', ['Qizil', 'M'], new Set())).toBe('ATLAS-QIZIL-M')
    expect(suggestSku('ATLAS', ['Qizil'], new Set(['ATLAS-QIZIL', 'ATLAS-QIZIL-2']))).toBe(
      'ATLAS-QIZIL-3',
    )
    const long = suggestSku('A'.repeat(60), ['BBBBBB'], new Set())
    expect(long.length).toBeLessThanOrEqual(64)
  })

  it('generates one row per combination and keeps edited rows on reselection', () => {
    let rows = syncRows(
      [],
      [{ attributeId: 'color', valueIds: ['red', 'blue'] }],
      attributes,
      'KOYLAK',
    )
    expect(rows.map((row) => row.sku)).toEqual(['KOYLAK-QIZIL', 'KOYLAK-KOK'])

    rows = rows.map((row) => (row.key === 'red' ? { ...row, price: '100 000' } : row))
    const selection = [
      { attributeId: 'color', valueIds: ['red', 'blue'] },
      { attributeId: 'size', valueIds: ['s', 'm'] },
    ]
    rows = syncRows(rows, selection, attributes, 'KOYLAK')
    expect(rows).toHaveLength(4)
    expect(rows.map((row) => row.labels.join('/'))).toEqual([
      'Qizil/S',
      'Qizil/M',
      "Ko'k/S",
      "Ko'k/M",
    ])
    // New sizes of a priced colour start with its price; stock is never copied.
    expect(rows.map((row) => row.price)).toEqual(['100 000', '100 000', '', ''])
    expect(rows.every((row) => row.stock === '0')).toBe(true)

    // Unpicking a value drops its new rows; an attribute without values is ignored.
    rows = syncRows(
      rows,
      [
        { attributeId: 'color', valueIds: ['red'] },
        { attributeId: 'size', valueIds: [] },
      ],
      attributes,
      'KOYLAK',
    )
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({ key: 'red', price: '100 000' })
  })

  it('makes one plain row for a product without attributes', () => {
    const rows = syncRows([], [], attributes, 'CHOYNAK')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({ key: BASE_KEY, sku: 'CHOYNAK', labels: [], stock: '0' })
  })

  it('never drops saved variants and only proposes combinations the seller adds', () => {
    const variants = [
      variant('v1', [
        ['red', 'Qizil'],
        ['s', 'S'],
      ]),
      variant(
        'v2',
        [
          ['blue', "Ko'k"],
          ['m', 'M'],
        ],
        { is_active: false, reserved: 2 },
      ),
    ]
    const { selection, rows } = initialMatrix(variants, attributes, 'KOYLAK')
    expect(selection).toEqual([
      { attributeId: 'color', valueIds: ['red', 'blue'] },
      { attributeId: 'size', valueIds: ['s', 'm'] },
    ])
    // 2 x 2 = 4 combinations: two saved, two not wanted yet (start removed).
    expect(rows).toHaveLength(4)
    expect(rows.filter((row) => !row.removed).map((row) => row.variantId)).toEqual(['v1'])
    expect(rows.find((row) => row.variantId === 'v2')).toMatchObject({ removed: true, reserved: 2 })
    expect([...lockedValueIds(rows)].sort()).toEqual(['blue', 'm', 'red', 's'])

    const narrowed = syncRows(rows, [{ attributeId: 'color', valueIds: ['red'] }], attributes, 'X')
    expect(narrowed.map((row) => row.variantId)).toEqual([null, 'v1', 'v2'])
  })

  it('follows title changes only for untouched generated SKUs', () => {
    const rows = syncRows(
      [],
      [{ attributeId: 'color', valueIds: ['red', 'blue'] }],
      attributes,
      'OLD',
    )
    const edited = rows.map((row) =>
      row.key === 'blue' ? { ...row, sku: 'MY-SKU', skuAuto: false } : row,
    )
    expect(refreshAutoSkus(edited, 'NEW').map((row) => row.sku)).toEqual(['NEW-QIZIL', 'MY-SKU'])
  })
})

const row = (patch: Partial<VariantRow>): VariantRow => ({
  key: 'k',
  valueIds: [],
  labels: [],
  variantId: null,
  sku: 'SKU-1',
  skuAuto: true,
  price: '10 000',
  stock: '1',
  removed: false,
  reserved: 0,
  original: null,
  ...patch,
})

describe('product form validation', () => {
  it('requires title and category', () => {
    const result = productSchema.safeParse({
      title: '  ',
      category_id: '',
      description: '',
      status: 'draft',
    })
    expect(result.success).toBe(false)
    const messages = result.success ? [] : result.error.issues.map((issue) => issue.message)
    expect(messages).toEqual(expect.arrayContaining(['titleRequired', 'categoryRequired']))
    expect(
      productSchema.safeParse({
        title: 'x'.repeat(201),
        category_id: 'c',
        description: '',
        status: 'draft',
      }).success,
    ).toBe(false)
  })

  it('checks every included row like the API does', () => {
    const rows = [
      row({ key: 'a', sku: '', price: '', stock: 'x' }),
      row({ key: 'b', sku: '-bad', price: '1,234' }),
      row({ key: 'c', sku: 'DUP' }),
      row({ key: 'd', sku: 'DUP', stock: '2', reserved: 3 }),
      row({ key: 'e', sku: '', removed: true }),
      row({ key: 'f', price: '0' }),
    ]
    const result = validateMatrix(rows, 'draft')
    expect(result.rows.a).toEqual({
      sku: { key: 'skuRequired' },
      price: { key: 'priceRequired' },
      stock: { key: 'stockInvalid' },
    })
    expect(result.rows.b).toEqual({ sku: { key: 'skuInvalid' }, price: { key: 'priceInvalid' } })
    expect(result.rows.c?.sku).toEqual({ key: 'skuDuplicate' })
    expect(result.rows.d?.stock).toEqual({ key: 'stockBelowReserved', params: { count: 3 } })
    expect(result.rows.e).toBeUndefined()
    expect(result.rows.f?.price).toEqual({ key: 'priceInvalid' })
    expect(hasMatrixErrors(result)).toBe(true)
  })

  it('needs at least one variant to sell, but a draft may have none', () => {
    expect(validateMatrix([row({ removed: true })], 'active').form).toEqual({ key: 'noVariants' })
    expect(validateMatrix([], 'draft')).toEqual({ rows: {}, form: null })
    expect(hasMatrixErrors(validateMatrix([row({})], 'active'))).toBe(false)
  })
})

describe('error mapping', () => {
  it('maps variant failures to the right field', () => {
    expect(variantFailure(new ApiError(409, 'SKU_TAKEN', 'x'))).toEqual({
      sku: { key: 'skuTaken' },
    })
    expect(variantFailure(new ApiError(409, 'STOCK_BELOW_RESERVED', 'x', { reserved: 4 }))).toEqual(
      { stock: { key: 'stockBelowReserved', params: { count: 4 } } },
    )
    expect(variantFailure(new ApiError(409, 'VARIANT_EXISTS', 'x'))).toEqual({
      row: { key: 'variantExists' },
    })
    expect(variantFailure(new ApiError(0, CLIENT_ERROR.NETWORK, 'x'))).toEqual({
      row: { key: 'network' },
    })
    expect(variantFailure('boom')).toEqual({ row: { key: 'unknown' } })
    expect(reservedFromError(new ApiError(409, 'STOCK_BELOW_RESERVED', 'x', { reserved: 2 }))).toBe(
      2,
    )
    expect(reservedFromError(new ApiError(409, 'SKU_TAKEN', 'x'))).toBeNull()
    expect(productSaveError(new ApiError(403, 'SELLER_NOT_FOUND', 'x'))).toEqual({
      key: 'shopNotReady',
    })
    expect(productSaveError(new ApiError(400, 'VALIDATION_ERROR', 'x'))).toEqual({
      key: 'rejected',
    })
  })
})

describe('categories', () => {
  it('flattens the tree depth first with indentation', () => {
    const options = flattenCategories([
      {
        id: '1',
        name: 'Kiyim',
        slug: 'kiyim',
        children: [{ id: '2', name: 'Ayollar', slug: 'ayollar', children: [] }],
      },
      { id: '3', name: 'Uy', slug: 'uy', children: [] },
    ])
    expect(options.map((option) => [option.name, option.depth, option.path])).toEqual([
      ['Kiyim', 0, 'Kiyim'],
      ['Ayollar', 1, 'Kiyim / Ayollar'],
      ['Uy', 0, 'Uy'],
    ])
    expect(indentedLabel(options[1]!)).toBe(`${String.fromCharCode(0xa0).repeat(3)}Ayollar`)
  })
})
