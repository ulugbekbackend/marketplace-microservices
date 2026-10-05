import { keepPreviousData, useQuery } from '@tanstack/react-query'
import type { ApiError } from '../errors'
import type { SearchParams, SearchResponse, Suggestion } from '../types'
import { useApi } from './context'
import { queryKeys } from './keys'

/** The suggest endpoint answers with an empty list below this many characters. */
export const SUGGEST_MIN_LENGTH = 2

/** Search results with facets; the previous page stays visible while the next one loads. */
export function useSearch(params: SearchParams, options: { enabled?: boolean } = {}) {
  const { search } = useApi()
  return useQuery<SearchResponse, ApiError>({
    queryKey: queryKeys.searchResults(params),
    queryFn: ({ signal }) => search.search(params, signal),
    placeholderData: keepPreviousData,
    enabled: options.enabled ?? true,
  })
}

/**
 * Title suggestions for a search box. Pass an already debounced value: every distinct `q`
 * is one request. Short queries never hit the network and yield an empty list.
 */
export function useSuggest(q: string) {
  const { search } = useApi()
  const term = q.trim()
  const enabled = term.length >= SUGGEST_MIN_LENGTH
  return useQuery<Suggestion[], ApiError>({
    queryKey: queryKeys.suggest(term),
    queryFn: async ({ signal }) => (await search.suggest(term, signal)).items,
    enabled,
    staleTime: 60_000,
    // A box that types ahead should not flicker or wait for retries: keep the last list.
    placeholderData: (previous) => (enabled ? previous : undefined),
    retry: false,
  })
}
