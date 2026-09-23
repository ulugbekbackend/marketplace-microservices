import { createApiClient, DEFAULT_API_URL, queryKeys, shouldRetry } from '@bozorcha/api-client'
import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: shouldRetry,
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: false },
  },
})

type SessionListener = () => void
const sessionExpiredListeners = new Set<SessionListener>()

/** Lets UI (e.g. a toast) react when the refresh token is rejected. */
export function onSessionExpired(listener: SessionListener): () => void {
  sessionExpiredListeners.add(listener)
  return () => sessionExpiredListeners.delete(listener)
}

export const apiClient = createApiClient({
  baseUrl: import.meta.env.VITE_API_URL || DEFAULT_API_URL,
  onSessionExpired: () => {
    queryClient.removeQueries({ queryKey: queryKeys.me })
    sessionExpiredListeners.forEach((listener) => listener())
  },
})
