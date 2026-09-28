import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { routes } from '../routes'
import { panelApi, productDetail, variant } from '../test/fixtures'
import { apiError, json, renderWithApi, type Route } from '../test/renderApp'

function setup(api: Record<string, Route> = {}, entry = '/products/new') {
  return renderWithApi(routes, { ...panelApi, ...api }, entry, { signedIn: true })
}

const saveButton = () => screen.getAllByRole('button', { name: 'Saqlash' })[0]!

const bodyOf = (call: [unknown, RequestInit?] | undefined) => JSON.parse(String(call![1]!.body))

describe('ProductEditorPage: validation', () => {
  it('shows field errors and sends nothing while the form is invalid', async () => {
    const u = userEvent.setup()
    const { fetchMock } = setup()
    await screen.findByRole('heading', { name: 'Yangi mahsulot' })
    const before = fetchMock.mock.calls.length
    await u.click(saveButton())
    expect(await screen.findByText('Mahsulot nomini kiriting')).toBeInTheDocument()
    expect(
      screen.getByText('Kategoriyani tanlang', { selector: '[role="alert"]' }),
    ).toBeInTheDocument()

    await u.type(screen.getByLabelText('Nomi'), 'Choynak')
    await u.selectOptions(screen.getByLabelText('Kategoriya'), 'c-ayollar')
    await u.click(saveButton())
    // The single plain variant still needs a price.
    expect(await screen.findByText('Narxni kiriting')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: "Narx, so'm: Asosiy" })).toHaveFocus()

    await u.type(screen.getByRole('textbox', { name: "Narx, so'm: Asosiy" }), '12,345')
    await u.click(saveButton())
    expect(await screen.findByText(/Narxni so'mda kiriting/)).toBeInTheDocument()

    const writes = fetchMock.mock.calls
      .slice(before)
      .filter(([, init]) => (init?.method ?? 'GET') !== 'GET')
    expect(writes).toHaveLength(0)
  })

  it('requires a variant before a product goes on sale', async () => {
    const u = userEvent.setup()
    setup()
    await u.type(await screen.findByLabelText('Nomi'), 'Choynak')
    await u.selectOptions(screen.getByLabelText('Kategoriya'), 'c-ayollar')
    await u.selectOptions(screen.getByLabelText('Mahsulot holati'), 'active')
    await u.click(screen.getByRole('button', { name: 'Olib tashlash: Asosiy' }))
    await u.click(saveButton())
    expect(
      await screen.findByText("Sotuvdagi mahsulotda kamida bitta variant bo'lishi kerak"),
    ).toBeInTheDocument()
  })
})

describe('ProductEditorPage: saving', () => {
  it('creates the product and one variant per combination, then enables uploads', async () => {
    const u = userEvent.setup()
    const created = productDetail({ id: 'p9', status: 'draft', variants: [], images: [] })
    let stored = created
    const { callsTo, router } = setup({
      'POST /api/catalog/seller/products/': () => json(201, created),
      'POST /api/catalog/seller/products/p9/variants/': (body) => {
        const b = body as { sku: string; price_tiyin: number; stock: number }
        const made = variant({
          id: `v-${b.sku}`,
          sku: b.sku,
          price_tiyin: b.price_tiyin,
          stock: b.stock,
          reserved: 0,
        })
        stored = { ...stored, variants: [...stored.variants, made] }
        return json(201, made)
      },
      'GET /api/catalog/seller/products/p9/': () => json(200, stored),
    })

    const upload = await screen.findByRole('button', { name: 'Fayl tanlash' })
    expect(upload).toBeDisabled()
    expect(screen.getByText('Rasm yuklash uchun avval mahsulotni saqlang')).toBeInTheDocument()

    await u.type(screen.getByLabelText('Nomi'), "Atlas ko'ylak")
    await u.selectOptions(screen.getByLabelText('Kategoriya'), 'c-ayollar')
    await u.selectOptions(screen.getByLabelText("Xususiyat qo'shish"), 'color')
    await u.click(screen.getByRole('button', { name: "Qo'shish" }))
    await u.click(screen.getByRole('button', { name: 'Qizil' }))
    await u.click(screen.getByRole('button', { name: "Ko'k" }))
    expect(screen.getByRole('button', { name: 'Qizil' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('2 ta variant')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'SKU: Qizil' })).toHaveValue('ATLAS-KOYLAK-QIZIL')

    await u.type(screen.getByLabelText('Hammasiga narx'), '450000')
    await u.type(screen.getByLabelText('Hammasiga qoldiq'), '7')
    await u.click(screen.getByRole('button', { name: "Qo'llash" }))
    expect(screen.getByRole('textbox', { name: "Narx, so'm: Ko'k" })).toHaveValue('450 000')

    await u.click(saveButton())
    await waitFor(() => expect(router.state.location.pathname).toBe('/products/p9'))
    expect(await screen.findByText('Mahsulot saqlandi')).toBeInTheDocument()

    expect(bodyOf(callsTo('POST', '/api/catalog/seller/products/')[0])).toEqual({
      title: "Atlas ko'ylak",
      description: '',
      category_id: 'c-ayollar',
      status: 'draft',
    })
    const variants = callsTo('POST', '/api/catalog/seller/products/p9/variants/').map(bodyOf)
    expect(variants).toEqual([
      {
        sku: 'ATLAS-KOYLAK-QIZIL',
        price_tiyin: 45_000_000,
        stock: 7,
        attribute_value_ids: ['red'],
      },
      { sku: 'ATLAS-KOYLAK-KOK', price_tiyin: 45_000_000, stock: 7, attribute_value_ids: ['blue'] },
    ])
    // Same form, now in edit mode: uploads are available and saved values are locked.
    expect(screen.getByRole('button', { name: 'Fayl tanlash' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Qizil' })).toBeDisabled()
  })

  it('marks a variant whose SKU is taken and saves the rest', async () => {
    const u = userEvent.setup()
    const product = productDetail({ variants: [variant()] })
    setup(
      {
        'GET /api/catalog/seller/products/p1/': () => json(200, product),
        'POST /api/catalog/seller/products/p1/variants/': () =>
          apiError(409, 'SKU_TAKEN', { sku: 'ATLAS-KOYLAK-KOK' }),
      },
      '/products/p1',
    )
    await u.click(await screen.findByRole('button', { name: "Ko'k" }))
    await u.type(screen.getByRole('textbox', { name: "Narx, so'm: Ko'k" }), '1000')
    await u.click(saveButton())
    expect(await screen.findByText('Bu SKU band, boshqasini kiriting')).toBeInTheDocument()
    expect(screen.getByText('Mahsulot saqlandi, lekin hammasi emas')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: "SKU: Ko'k" })).toHaveAttribute(
      'aria-invalid',
      'true',
    )
  })

  it('shows not found for a product of another shop', async () => {
    setup(
      { 'GET /api/catalog/seller/products/zzz/': () => apiError(404, 'NOT_FOUND') },
      '/products/zzz',
    )
    expect(await screen.findByText('Mahsulot topilmadi')).toBeInTheDocument()
  })
})

/** XHR double: the test decides when the upload progresses and finishes. */
class FakeXhr {
  static instances: FakeXhr[] = []
  upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null }
  status = 0
  method = ''
  url = ''
  headers: Record<string, string> = {}
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  onabort: (() => void) | null = null
  constructor() {
    FakeXhr.instances.push(this)
  }
  open(method: string, url: string) {
    this.method = method
    this.url = url
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value
  }
  send() {}
  abort() {}
}

describe('ProductEditorPage: images', () => {
  beforeEach(() => {
    FakeXhr.instances = []
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
    URL.createObjectURL = vi.fn(() => 'blob:preview')
    URL.revokeObjectURL = vi.fn()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('uploads with progress, then shows processing until the image is ready', async () => {
    const processing = {
      id: 'img1',
      position: 0,
      status: 'processing' as const,
      original_key: 'products/p1/a.png',
      thumb_url: null,
      medium_url: null,
      large_url: null,
      created_at: '2026-09-01T00:00:00Z',
    }
    let images: (typeof processing | { status: 'ready'; thumb_url: string })[] = []
    const { callsTo } = setup(
      {
        'GET /api/catalog/seller/products/p1/': () =>
          json(200, productDetail({ images: images as never })),
        'POST /api/catalog/seller/uploads/presign/': () =>
          json(200, {
            upload_url: 'http://s3.test/bucket/products/p1/a.png?sig=1',
            key: 'products/p1/a.png',
            headers: { 'Content-Type': 'image/png' },
            method: 'PUT',
            expires_in: 600,
          }),
        'POST /api/catalog/seller/products/p1/images/': () => {
          images = [processing]
          return json(202, processing)
        },
      },
      '/products/p1',
    )
    const input = await screen.findByTestId('image-input')
    const file = new File(['png'], 'atlas.png', { type: 'image/png' })
    const bad = new File(['gif'], 'anim.gif', { type: 'image/gif' })
    fireEvent.change(input, { target: { files: [file, bad] } })

    expect(
      await screen.findByText('Faqat JPG, PNG yoki WEBP rasm yuklash mumkin'),
    ).toBeInTheDocument()
    await waitFor(() => expect(FakeXhr.instances).toHaveLength(1))
    expect(bodyOf(callsTo('POST', '/api/catalog/seller/uploads/presign/')[0])).toEqual({
      product_id: 'p1',
      filename: 'atlas.png',
      content_type: 'image/png',
      size: 3,
    })
    const xhr = FakeXhr.instances[0]!
    expect(xhr.method).toBe('PUT')
    expect(xhr.headers).toEqual({ 'Content-Type': 'image/png' })

    act(() =>
      xhr.upload.onprogress?.({ lengthComputable: true, loaded: 30, total: 100 } as ProgressEvent),
    )
    const list = screen.getByRole('list', { name: 'Mahsulot rasmlari' })
    expect(within(list).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '30')

    act(() => {
      xhr.status = 200
      xhr.onload?.()
    })
    // Attached: the server image is processed; the local preview stands in meanwhile.
    await waitFor(() => {
      const tile = within(list).getByRole('img', { name: '1-rasm' })
      expect(tile).toHaveAttribute('src', 'blob:preview')
      expect(tile.closest('li')).toHaveAttribute('data-status', 'processing')
    })
    expect(within(list).getByText('Tayyorlanmoqda')).toBeInTheDocument()
    expect(bodyOf(callsTo('POST', '/api/catalog/seller/products/p1/images/')[0])).toEqual({
      key: 'products/p1/a.png',
    })

    images = [{ ...processing, status: 'ready', thumb_url: 'http://s3.test/thumb.webp' }]
    // The product is polled every 2 s while an image is processing.
    await waitFor(
      () => {
        const tile = within(list).getByRole('img', { name: '1-rasm' })
        expect(tile).toHaveAttribute('src', 'http://s3.test/thumb.webp')
        expect(tile.closest('li')).toHaveAttribute('data-status', 'ready')
      },
      { timeout: 5000 },
    )
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview')
  }, 10_000)
})
