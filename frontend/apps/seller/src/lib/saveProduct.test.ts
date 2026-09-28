import {
  ApiError,
  type sellerCatalogEndpoints,
  type SellerProductDetail,
} from '@bozorcha/api-client'
import { describe, expect, it, vi } from 'vitest'
import { productSaveError, saveProduct, variantFailure } from './saveProduct'
import type { VariantRow } from './variantMatrix'

type SellerApi = ReturnType<typeof sellerCatalogEndpoints>

const product = (patch: Partial<SellerProductDetail> = {}): SellerProductDetail => ({
  id: 'p1',
  slug: 'choynak',
  title: 'Choynak',
  status: 'draft',
  category: { id: 'c1', name: 'Idish', slug: 'idish' },
  min_price_tiyin: null,
  max_price_tiyin: null,
  in_stock: false,
  variants_count: 0,
  stock_total: 0,
  reserved_total: 0,
  image_url: null,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  description: '',
  variants: [],
  images: [],
  ...patch,
})

const serverVariant = (id: string, sku: string, price: number, stock: number) => ({
  id,
  sku,
  price_tiyin: price,
  stock,
  reserved: 0,
  available: stock,
  is_active: true,
  attributes: [],
  created_at: '',
  updated_at: '',
})

const row = (patch: Partial<VariantRow>): VariantRow => ({
  key: 'k',
  valueIds: [],
  labels: [],
  variantId: null,
  sku: 'SKU',
  skuAuto: true,
  price: '125 000',
  stock: '3',
  removed: false,
  reserved: 0,
  original: null,
  ...patch,
})

function fakeApi(overrides: Partial<Record<keyof SellerApi, ReturnType<typeof vi.fn>>> = {}) {
  return {
    createProduct: vi.fn(async () => product()),
    updateProduct: vi.fn(async () => product()),
    createVariant: vi.fn(
      async (_id: string, body: { sku: string; price_tiyin: number; stock: number }) =>
        serverVariant(`v-${body.sku}`, body.sku, body.price_tiyin, body.stock),
    ),
    updateVariant: vi.fn(async (id: string, body: { sku?: string; price_tiyin?: number }) =>
      serverVariant(id, body.sku ?? 'OLD', body.price_tiyin ?? 100, 5),
    ),
    setStock: vi.fn(async (id: string, body: { stock: number }) =>
      serverVariant(id, 'OLD', 100, body.stock),
    ),
    product: vi.fn(async () => product({ status: 'active' })),
    ...overrides,
  }
}

const asApi = (mocks: ReturnType<typeof fakeApi>) => mocks as unknown as SellerApi

const values = { title: ' Choynak ', category_id: 'c1', description: '', status: 'active' as const }

describe('saveProduct', () => {
  it('creates the product as a draft, then its variants, then puts it on sale', async () => {
    const api = fakeApi()
    const result = await saveProduct(asApi(api), {
      productId: null,
      values,
      baseline: null,
      rows: [
        row({ key: 'red', sku: 'CH-RED', price: '125 000,50', valueIds: ['red'] }),
        row({ key: 'blue', sku: 'CH-BLUE', removed: true }),
      ],
    })
    expect(api.createProduct).toHaveBeenCalledWith({
      title: 'Choynak',
      description: '',
      category_id: 'c1',
      status: 'draft',
    })
    expect(api.createVariant).toHaveBeenCalledTimes(1)
    expect(api.updateProduct).toHaveBeenCalledExactlyOnceWith('p1', { status: 'active' })
    expect(api.updateProduct.mock.invocationCallOrder[0]).toBeGreaterThan(
      api.createVariant.mock.invocationCallOrder[0]!,
    )
    expect(result.activation).toBeNull()
    expect(api.createVariant).toHaveBeenCalledWith('p1', {
      sku: 'CH-RED',
      price_tiyin: 12_500_050,
      stock: 3,
      attribute_value_ids: ['red'],
    })
    expect(result.failures).toEqual({})
    expect(result.rows[0]).toMatchObject({ variantId: 'v-CH-RED', skuAuto: false })
    expect(result.rows[0]!.original).toEqual({
      sku: 'CH-RED',
      priceTiyin: 12_500_050,
      stock: 3,
      active: true,
    })
    expect(result.product.status).toBe('active')
  })

  it('sends only what changed on existing variants and product', async () => {
    const api = fakeApi()
    const original = { sku: 'OLD', priceTiyin: 100, stock: 5, active: true }
    await saveProduct(asApi(api), {
      productId: 'p1',
      values: { ...values, title: 'Choynak' },
      baseline: product(),
      rows: [
        row({ key: 'same', variantId: 'v1', sku: 'OLD', price: '1', stock: '5', original }),
        row({ key: 'price', variantId: 'v2', sku: 'OLD', price: '2', stock: '5', original }),
        row({ key: 'stock', variantId: 'v3', sku: 'OLD', price: '1', stock: '9', original }),
        row({
          key: 'off',
          variantId: 'v4',
          sku: 'OLD',
          price: '1',
          stock: '9',
          removed: true,
          original,
        }),
      ],
    })
    // Going on sale is sent last, after every variant change.
    expect(api.updateProduct).toHaveBeenCalledExactlyOnceWith('p1', { status: 'active' })
    expect(api.updateProduct.mock.invocationCallOrder[0]).toBeGreaterThan(
      Math.max(
        ...api.updateVariant.mock.invocationCallOrder,
        ...api.setStock.mock.invocationCallOrder,
      ),
    )
    expect(api.updateVariant.mock.calls).toEqual([
      ['v2', { price_tiyin: 200 }],
      ['v4', { is_active: false }],
    ])
    expect(api.setStock.mock.calls).toEqual([['v3', { stock: 9 }]])
  })

  it('keeps going after a failing variant and reports it on the row', async () => {
    const api = fakeApi({
      createVariant: vi.fn(async (_id: string, body: { sku: string }) => {
        if (body.sku === 'TAKEN') throw new ApiError(409, 'SKU_TAKEN', 'taken', { sku: 'TAKEN' })
        return serverVariant('v-ok', body.sku, 100, 1)
      }),
      setStock: vi.fn(async () => {
        throw new ApiError(409, 'STOCK_BELOW_RESERVED', 'x', { reserved: 4 })
      }),
    })
    const original = { sku: 'OLD', priceTiyin: 100, stock: 5, active: true }
    const result = await saveProduct(asApi(api), {
      productId: 'p1',
      values: { ...values, title: 'Choynak', status: 'draft' },
      baseline: product(),
      rows: [
        row({ key: 'a', sku: 'TAKEN' }),
        row({ key: 'b', sku: 'FREE' }),
        row({ key: 'c', variantId: 'v3', sku: 'OLD', price: '2', stock: '1', original }),
      ],
    })
    expect(result.failures).toEqual({
      a: { sku: { key: 'skuTaken' } },
      c: { stock: { key: 'stockBelowReserved', params: { count: 4 } } },
    })
    expect(result.rows.map((r) => r.variantId)).toEqual([null, 'v-ok', 'v3'])
    // The price change went through and is the new baseline; the stock stays unsaved.
    expect(result.rows[2]!.original?.priceTiyin).toBe(200)
    expect(result.rows[2]!.stock).toBe('1')
  })

  it('throws when the product itself cannot be saved', async () => {
    const api = fakeApi({
      createProduct: vi.fn(async () => {
        throw new ApiError(400, 'VALIDATION_ERROR', 'bad')
      }),
    })
    await expect(
      saveProduct(asApi(api), { productId: null, values, baseline: null, rows: [row({})] }),
    ).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    expect(api.createVariant).not.toHaveBeenCalled()
  })

  it('takes a product off sale before touching the variants', async () => {
    const api = fakeApi()
    const original = { sku: 'OLD', priceTiyin: 100, stock: 5, active: true }
    await saveProduct(asApi(api), {
      productId: 'p1',
      values: { ...values, title: 'Choynak', status: 'draft' },
      baseline: product({ status: 'active' }),
      rows: [row({ key: 'off', variantId: 'v1', sku: 'OLD', price: '1', removed: true, original })],
    })
    expect(api.updateProduct).toHaveBeenCalledExactlyOnceWith('p1', { status: 'draft' })
    expect(api.updateProduct.mock.invocationCallOrder[0]).toBeLessThan(
      api.updateVariant.mock.invocationCallOrder[0]!,
    )
  })

  it('sends other product changes first and the activation last', async () => {
    const api = fakeApi()
    const original = { sku: 'OLD', priceTiyin: 100, stock: 5, active: true }
    await saveProduct(asApi(api), {
      productId: 'p1',
      values: { ...values, title: 'Yangi choynak' },
      baseline: product(),
      rows: [row({ key: 'a', variantId: 'v1', sku: 'OLD', price: '1', stock: '5', original })],
    })
    expect(api.updateProduct.mock.calls).toEqual([
      ['p1', { title: 'Yangi choynak' }],
      ['p1', { status: 'active' }],
    ])
  })

  it('keeps a new product as a draft when no variant got saved', async () => {
    const api = fakeApi({
      createVariant: vi.fn(async () => {
        throw new ApiError(409, 'SKU_TAKEN', 'taken')
      }),
      product: vi.fn(async () => product()),
    })
    const result = await saveProduct(asApi(api), {
      productId: null,
      values,
      baseline: null,
      rows: [row({ key: 'a', sku: 'TAKEN' })],
    })
    expect(api.updateProduct).not.toHaveBeenCalled()
    expect(result.activation).toEqual({ key: 'activateNoVariant' })
    expect(result.product.status).toBe('draft')
    expect(result.failures.a).toEqual({ sku: { key: 'skuTaken' } })
  })

  it('keeps what was saved when the activation is refused, with the server reason', async () => {
    const reason = 'A product needs at least one active variant before it can be active.'
    const api = fakeApi({
      updateProduct: vi.fn(async () => {
        throw new ApiError(400, 'VALIDATION_ERROR', 'bad', { status: [reason] })
      }),
      product: vi.fn(async () => product()),
    })
    const result = await saveProduct(asApi(api), {
      productId: null,
      values,
      baseline: null,
      rows: [row({ key: 'a', sku: 'CH-1' })],
    })
    expect(result.activation).toEqual({ key: 'activateRejected', params: { message: reason } })
    expect(result.rows[0]!.variantId).toBe('v-CH-1')
    expect(result.product.id).toBe('p1')
  })

  it('reports a failed activation without a reason as a plain message', async () => {
    const api = fakeApi({
      updateProduct: vi.fn(async () => {
        throw new ApiError(503, 'SERVICE_UNAVAILABLE', 'down')
      }),
    })
    const result = await saveProduct(asApi(api), {
      productId: null,
      values,
      baseline: null,
      rows: [row({ key: 'a', sku: 'CH-1' })],
    })
    expect(result.activation).toEqual({ key: 'activateFailed' })
  })
})

describe('save errors', () => {
  it('maps the last active variant rule to the row', () => {
    const error = new ApiError(409, 'LAST_ACTIVE_VARIANT', 'x', { variant_id: 'v1' })
    expect(variantFailure(error)).toEqual({ row: { key: 'lastActiveVariant' } })
  })

  it('shows the server status message of a 400', () => {
    const reason = 'A product needs at least one active variant before it can be active.'
    expect(
      productSaveError(new ApiError(400, 'VALIDATION_ERROR', 'x', { status: [reason] })),
    ).toEqual({ key: 'statusRejected', params: { message: reason } })
    expect(
      productSaveError(new ApiError(400, 'VALIDATION_ERROR', 'x', { title: ['required'] })),
    ).toEqual({ key: 'rejected' })
  })
})
