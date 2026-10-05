import { describe, expect, it } from 'vitest'
import i18n from '../i18n'
import {
  activeFilterCount,
  bucketRange,
  catalogHref,
  isBucketSelected,
  parseCatalogParams,
  toCatalogParams,
  toggleAttr,
  toSearchParams,
  withFilters,
} from './catalogFilters'
import { priceBucketLabel, priceRangeLabel } from './searchLabels'

const parse = (query: string) => parseCatalogParams(new URLSearchParams(query))
const plain = (text: string) => text.replaceAll(String.fromCharCode(0xa0), ' ')

describe('catalog URL state', () => {
  it('parses every filter and ignores junk', () => {
    expect(
      parse(
        'q=+futbolka+&sort=price_asc&price_min=100&price_max=abc&in_stock=1&page=3' +
          '&attr[color]=qizil&attr[color]=qora&attr[color]=qizil&attr[size]=&x=1',
      ),
    ).toEqual({
      q: 'futbolka',
      page: 3,
      sort: 'price_asc',
      priceMin: 100,
      priceMax: null,
      inStock: true,
      attrs: { color: ['qizil', 'qora'] },
    })
    expect(parse('sort=cheapest&page=-2')).toMatchObject({ sort: null, page: 1 })
  })

  it('writes a canonical query string and round-trips it', () => {
    const filters = parse('attr[size]=M&attr[color]=qora&attr[color]=oq&in_stock=true&q=ko%27ylak')
    const query = toCatalogParams(filters).toString()
    expect(decodeURIComponent(query)).toBe(
      "q=ko'ylak&in_stock=1&attr[color]=oq&attr[color]=qora&attr[size]=M",
    )
    const again = parseCatalogParams(new URLSearchParams(query))
    expect(again).toEqual({ ...filters, attrs: { color: ['oq', 'qora'], size: ['M'] } })
    expect(toCatalogParams(again).toString()).toBe(query)
  })

  it('leaves the default order out of the URL', () => {
    expect(toCatalogParams(parse('sort=newest')).has('sort')).toBe(false)
    expect(toCatalogParams(parse('q=a&sort=relevance')).has('sort')).toBe(false)
    expect(toCatalogParams(parse('q=a&sort=newest')).get('sort')).toBe('newest')
    // relevance needs a query to rank by
    expect(toSearchParams(parse('sort=relevance'), undefined).sort).toBe('newest')
  })

  it('starts from page 1 after any filter change', () => {
    const filters = parse('page=4&attr[color]=qora')
    expect(toggleAttr(filters, 'color', 'oq')).toMatchObject({
      page: 1,
      attrs: { color: ['qora', 'oq'] },
    })
    expect(toggleAttr(filters, 'color', 'qora').attrs).toEqual({})
    expect(withFilters(filters, { inStock: true }).page).toBe(1)
    expect(catalogHref('kiyim', { ...filters, page: 2 })).toBe(
      '/catalog/kiyim?attr%5Bcolor%5D=qora&page=2',
    )
  })

  it('builds API params with the category id', () => {
    expect(toSearchParams(parse('q=telefon&in_stock=1&attr[memory]=128 GB'), 'c1')).toEqual({
      q: 'telefon',
      category: 'c1',
      price_min: undefined,
      price_max: undefined,
      in_stock: true,
      attr: { memory: ['128 GB'] },
      sort: 'relevance',
      page: 1,
      page_size: 24,
    })
  })
})

describe('price buckets', () => {
  const bucket = { key: '100k_500k', from_tiyin: 10_000_000, to_tiyin: 50_000_000, count: 3 }
  const open = { key: 'gte_5m', from_tiyin: 500_000_000, to_tiyin: null, count: 1 }

  it('turns the exclusive upper bound into an inclusive price_max', () => {
    expect(bucketRange(bucket)).toEqual({ priceMin: 10_000_000, priceMax: 49_999_999 })
    expect(bucketRange(open)).toEqual({ priceMin: 500_000_000, priceMax: null })
    const filters = withFilters(parse(''), bucketRange(bucket))
    expect(isBucketSelected(bucket, filters)).toBe(true)
    expect(isBucketSelected(open, filters)).toBe(false)
    expect(activeFilterCount(filters)).toBe(1)
  })

  it('labels buckets and URL ranges with round numbers', () => {
    const t = i18n.t.bind(i18n)
    expect(plain(priceBucketLabel(t, bucket))).toBe("100 000 – 500 000 so'm")
    expect(plain(priceBucketLabel(t, open))).toBe("5 000 000 so'mdan")
    expect(plain(priceBucketLabel(t, { ...bucket, from_tiyin: null }))).toBe("500 000 so'mgacha")
    expect(plain(priceRangeLabel(t, 10_000_000, 49_999_999))).toBe("100 000 – 500 000 so'm")
  })
})
