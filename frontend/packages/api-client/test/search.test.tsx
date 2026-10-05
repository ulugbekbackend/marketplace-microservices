import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { createApiClient } from '../src/client'
import { searchQuery } from '../src/endpoints'
import { ApiProvider } from '../src/hooks/context'
import { useSearch, useSuggest } from '../src/hooks/search'
import { TokenStore } from '../src/tokens'
import type { SearchResponse } from '../src/types'
import { errorBody, fakeFetch, json, memoryStorage, type Handler } from './fakeServer'

const SEARCH = '/api/search'
const SUGGEST = '/api/search/suggest'

const emptyResult = (page = 1): SearchResponse => ({
  items: [],
  total: 0,
  page,
  page_size: 24,
  facets: { categories: [], price_ranges: [], attributes: [] },
})

function setup(routes: Record<string, Handler>) {
  const server = fakeFetch(routes)
  const client = createApiClient({
    baseUrl: 'http://api.test',
    tokens: new TokenStore(memoryStorage()),
    fetch: server.fetch,
  })
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={client}>{children}</ApiProvider>
    </QueryClientProvider>
  )
  return { server, wrapper }
}

describe('searchQuery', () => {
  it('turns attr into sorted, de-duplicated repeated keys and drops empty codes', () => {
    expect(
      searchQuery({ q: 'futbolka', attr: { size: ['M'], color: ['red', 'blue', 'red'], x: [] } }),
    ).toEqual({ q: 'futbolka', 'attr[color]': ['blue', 'red'], 'attr[size]': ['M'] })
  })
})

describe('useSearch', () => {
  it('sends every filter, attr values as repeated keys', async () => {
    const { server, wrapper } = setup({ [`GET ${SEARCH}`]: () => json(200, emptyResult(2)) })
    const { result } = renderHook(
      () =>
        useSearch({
          q: 'futbolka',
          category: 'c1',
          price_min: 10_000_000,
          price_max: 49_999_999,
          in_stock: true,
          attr: { color: ['qizil', "ko'k"] },
          sort: 'price_asc',
          page: 2,
          page_size: 24,
        }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const url = server.callsTo('GET', SEARCH)[0]!.url
    expect(url.searchParams.getAll('attr[color]')).toEqual(["ko'k", 'qizil'])
    expect(url.searchParams.get('q')).toBe('futbolka')
    expect(url.searchParams.get('category')).toBe('c1')
    expect(url.searchParams.get('price_min')).toBe('10000000')
    expect(url.searchParams.get('price_max')).toBe('49999999')
    expect(url.searchParams.get('in_stock')).toBe('true')
    expect(url.searchParams.get('sort')).toBe('price_asc')
    expect(url.searchParams.get('page')).toBe('2')
  })

  it('surfaces SEARCH_UNAVAILABLE as an ApiError', async () => {
    const { wrapper } = setup({
      [`GET ${SEARCH}`]: () => json(503, errorBody('SEARCH_UNAVAILABLE')),
    })
    const { result } = renderHook(() => useSearch({ q: 'x' }), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error?.status).toBe(503)
    expect(result.current.error?.code).toBe('SEARCH_UNAVAILABLE')
  })
})

describe('useSuggest', () => {
  const items = [{ id: 'p1', slug: 'basic-futbolka', title: 'Basic futbolka' }]

  it('does not call the API for queries shorter than 2 characters', async () => {
    const { server, wrapper } = setup({ [`GET ${SUGGEST}`]: () => json(200, { items }) })
    const { result } = renderHook(() => useSuggest(' f '), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
    expect(result.current.data).toBeUndefined()
    expect(server.callsTo('GET', SUGGEST)).toHaveLength(0)
  })

  it('returns the suggestion list for a trimmed query', async () => {
    const { server, wrapper } = setup({ [`GET ${SUGGEST}`]: () => json(200, { items }) })
    const { result } = renderHook(() => useSuggest('  fut '), { wrapper })
    await waitFor(() => expect(result.current.data).toEqual(items))
    expect(server.callsTo('GET', SUGGEST)[0]!.url.searchParams.get('q')).toBe('fut')
  })

  it('keeps the previous list while the next query loads', async () => {
    const { wrapper } = setup({
      [`GET ${SUGGEST}`]: (req) =>
        json(200, {
          items: req.url.searchParams.get('q') === 'fut' ? items : [],
        }),
    })
    const { result, rerender } = renderHook(({ q }) => useSuggest(q), {
      wrapper,
      initialProps: { q: 'fut' },
    })
    await waitFor(() => expect(result.current.data).toEqual(items))
    rerender({ q: 'futb' })
    expect(result.current.data).toEqual(items)
    expect(result.current.isPlaceholderData).toBe(true)
    await waitFor(() => expect(result.current.data).toEqual([]))
  })
})
