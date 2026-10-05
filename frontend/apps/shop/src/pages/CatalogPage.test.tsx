import type { Category, SearchItem, SearchResponse } from '@bozorcha/api-client'
import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { apiError, json, renderWithApi, type Route } from '../test/renderApp'
import { CatalogPage } from './CatalogPage'

const categories: Category[] = [
  {
    id: 'c1',
    name: 'Kiyim',
    slug: 'kiyim',
    children: [
      {
        id: 'c2',
        name: 'Erkaklar kiyimi',
        slug: 'erkaklar-kiyimi',
        children: [{ id: 'c3', name: 'Futbolkalar', slug: 'futbolkalar', children: [] }],
      },
      { id: 'c5', name: 'Ayollar kiyimi', slug: 'ayollar-kiyimi', children: [] },
    ],
  },
  { id: 'c4', name: 'Elektronika', slug: 'elektronika', children: [] },
]

const item = (n: number, extra: Partial<SearchItem> = {}): SearchItem => ({
  id: `p${n}`,
  slug: `futbolka-${n}`,
  title: `Futbolka ${n}`,
  seller_id: 's1',
  shop_name: 'Oqtepa Savdo',
  min_price: 190_000_00,
  max_price: 190_000_00,
  in_stock: true,
  image_url: null,
  rating: 0,
  ...extra,
})

function result(url: URL): SearchResponse {
  const colors = url.searchParams.getAll('attr[color]')
  const items = [
    item(1, { min_price: 150_000_00, max_price: 210_000_00 }),
    item(2, { in_stock: false }),
  ]
  return {
    items: url.searchParams.get('in_stock') === 'true' ? items.slice(0, 1) : items,
    total: 30,
    page: Number(url.searchParams.get('page') ?? 1),
    page_size: 24,
    facets: {
      categories: [
        { id: 'c1', name: 'Kiyim', count: 30 },
        { id: 'c2', name: 'Erkaklar kiyimi', count: 30 },
        { id: 'c3', name: 'Futbolkalar', count: 12 },
        { id: 'c4', name: 'Elektronika', count: 4 },
      ],
      price_ranges: [
        { key: 'lt_100k', from_tiyin: null, to_tiyin: 10_000_000, count: 0 },
        { key: '100k_500k', from_tiyin: 10_000_000, to_tiyin: 50_000_000, count: 30 },
      ],
      attributes: [
        {
          code: 'color',
          values: [
            { value: 'qizil', count: 6, selected: colors.includes('qizil') },
            { value: 'qora', count: 4, selected: colors.includes('qora') },
          ],
        },
      ],
    },
  }
}

const routes = [
  { path: '/catalog/:categorySlug?', element: <CatalogPage /> },
  { path: '/p/:slug', element: <p>Mahsulot sahifasi</p> },
]

function setup(entry: string, search: Route = (_body, url) => json(200, result(url))) {
  const view = renderWithApi(
    routes,
    {
      'GET /api/catalog/categories/': () => json(200, categories),
      'GET /api/search': search,
    },
    entry,
  )
  const searches = () => view.callsTo('GET', '/api/search').map(([input]) => new URL(String(input)))
  const lastSearch = () => searches().at(-1)!
  return { ...view, searches, lastSearch }
}

const plain = (text: string | null) => (text ?? '').replaceAll(String.fromCharCode(0xa0), ' ')

describe('CatalogPage', () => {
  it('lists a category through the search API by category id', async () => {
    const { lastSearch } = setup('/catalog/kiyim')
    expect(await screen.findByRole('heading', { level: 1, name: 'Kiyim' })).toBeInTheDocument()
    await screen.findByText('Futbolka 1')
    expect(Object.fromEntries(lastSearch().searchParams)).toEqual({
      category: 'c1',
      sort: 'newest',
      page: '1',
      page_size: '24',
    })
    expect(screen.getByText('30 ta mahsulot')).toBeInTheDocument()
    // price range on the card, out-of-stock badge
    const cards = screen.getByRole('list', { name: "Mahsulotlar ro'yxati" })
    expect(plain(within(cards).getAllByTestId('price')[0]!.textContent)).toBe("150 000 so'm")
    expect(within(cards).getByText('dan')).toBeInTheDocument()
    expect(within(cards).getByText('Tugagan')).toBeInTheDocument()
    // category drill-down: children with hits, link back up
    const nav = screen.getByRole('navigation', { name: 'Kategoriya' })
    expect(within(nav).getByRole('link', { name: /Erkaklar kiyimi/ })).toHaveAttribute(
      'href',
      '/catalog/erkaklar-kiyimi',
    )
    expect(within(nav).queryByRole('link', { name: /Ayollar kiyimi/ })).not.toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: 'Barcha kategoriyalar' })).toHaveAttribute(
      'href',
      '/catalog',
    )
  })

  it('applies facet filters through the URL and restores them with the back button', async () => {
    const u = userEvent.setup()
    const { router, lastSearch } = setup('/catalog?page=2')
    await screen.findByText('Futbolka 1')

    await u.click(screen.getByRole('checkbox', { name: /^Qizil/ }))
    await waitFor(() => expect(lastSearch().searchParams.getAll('attr[color]')).toEqual(['qizil']))
    expect(router.state.location.search).toBe('?attr%5Bcolor%5D=qizil')
    expect(lastSearch().searchParams.get('page')).toBe('1')

    await u.click(screen.getByRole('checkbox', { name: /^Qora/ }))
    await waitFor(() =>
      expect(lastSearch().searchParams.getAll('attr[color]')).toEqual(['qizil', 'qora']),
    )

    const bucket = screen.getByRole('radio', { name: /^100.000 – 500.000.so'm/ })
    expect(screen.getByRole('radio', { name: /so'mgacha/ })).toBeDisabled()
    await u.click(bucket)
    await waitFor(() => expect(lastSearch().searchParams.get('price_max')).toBe('49999999'))
    expect(lastSearch().searchParams.get('price_min')).toBe('10000000')
    expect(bucket).toBeChecked()

    await u.click(screen.getByRole('checkbox', { name: 'Faqat sotuvdagilar' }))
    await waitFor(() => expect(lastSearch().searchParams.get('in_stock')).toBe('true'))
    expect(screen.getByRole('button', { name: 'Filtrlar (4)' })).toBeInTheDocument()

    // back: the stock filter goes, the price stays
    await act(() => router.navigate(-1))
    await waitFor(() => expect(lastSearch().searchParams.has('in_stock')).toBe(false))
    expect(screen.getByRole('checkbox', { name: 'Faqat sotuvdagilar' })).not.toBeChecked()
    expect(screen.getByRole('radio', { name: /^100.000 – 500.000.so'm/ })).toBeChecked()

    // chips remove one filter each
    const chips = screen.getByRole('list', { name: 'Tanlangan filtrlar' })
    await u.click(within(chips).getByRole('button', { name: 'Olib tashlash: Rang: Qizil' }))
    await waitFor(() => expect(lastSearch().searchParams.getAll('attr[color]')).toEqual(['qora']))
    await u.click(within(chips).getByRole('button', { name: 'Filtrlarni tozalash' }))
    await waitFor(() => expect(router.state.location.search).toBe(''))
  })

  it('sorts, and shows search results for a query', async () => {
    const u = userEvent.setup()
    const { router, lastSearch } = setup('/catalog?q=futbolka')
    expect(
      await screen.findByRole('heading', { level: 1, name: '"futbolka" bo\'yicha natijalar' }),
    ).toBeInTheDocument()
    await screen.findByText('Futbolka 1')
    expect(lastSearch().searchParams.get('q')).toBe('futbolka')
    expect(lastSearch().searchParams.get('sort')).toBe('relevance')

    await u.selectOptions(screen.getByRole('combobox', { name: 'Saralash' }), 'price_asc')
    await waitFor(() => expect(lastSearch().searchParams.get('sort')).toBe('price_asc'))
    expect(router.state.location.search).toBe('?q=futbolka&sort=price_asc')

    await u.click(screen.getByRole('link', { name: 'Qidiruvni tozalash' }))
    await waitFor(() => expect(router.state.location.search).toBe('?sort=price_asc'))
  })

  it('keeps the query but drops attributes when moving to another category', async () => {
    setup('/catalog/kiyim?q=futbolka&attr[color]=qizil&in_stock=1')
    const nav = await screen.findByRole('navigation', { name: 'Kategoriya' })
    expect(within(nav).getByRole('link', { name: /Erkaklar kiyimi/ })).toHaveAttribute(
      'href',
      '/catalog/erkaklar-kiyimi?q=futbolka&in_stock=1',
    )
  })

  it('offers to clear filters when nothing matches', async () => {
    const u = userEvent.setup()
    const { router } = setup('/catalog?attr[color]=qora', (_body, url) =>
      json(200, {
        ...result(url),
        items: url.searchParams.has('attr[color]') ? [] : [item(1)],
        total: url.searchParams.has('attr[color]') ? 0 : 1,
      }),
    )
    expect(await screen.findByText("Tanlangan filtrlarga mos mahsulot yo'q")).toBeInTheDocument()
    const empty = screen.getByText("Tanlangan filtrlarga mos mahsulot yo'q").parentElement!
    await u.click(within(empty).getByRole('button', { name: 'Filtrlarni tozalash' }))
    expect(await screen.findByText('Futbolka 1')).toBeInTheDocument()
    expect(router.state.location.search).toBe('')
  })

  it('says the search is down on 503 and retries', async () => {
    const u = userEvent.setup()
    let down = true
    setup('/catalog', (_body, url) =>
      down ? apiError(503, 'SEARCH_UNAVAILABLE') : json(200, result(url)),
    )
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Qidiruv vaqtincha ishlamayapti')).toBeInTheDocument()
    down = false
    await u.click(within(alert).getByRole('button', { name: 'Qayta urinish' }))
    expect(await screen.findByText('Futbolka 1')).toBeInTheDocument()
  })

  it('shows not found for an unknown category without searching', async () => {
    const { searches } = setup('/catalog/yoq-narsa')
    expect(await screen.findByText('Bunday kategoriya topilmadi')).toBeInTheDocument()
    expect(searches()).toHaveLength(0)
  })
})
