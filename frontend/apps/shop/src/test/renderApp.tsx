import { ApiProvider, createApiClient, TokenStore, type TokenStorage } from '@bozorcha/api-client'
import { ToastProvider } from '@bozorcha/ui'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { createMemoryRouter, type RouteObject } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { vi } from 'vitest'

export type Route = (body: unknown, url: URL) => Response | Promise<Response>

export const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

export const apiError = (status: number, code: string, details?: unknown) =>
  json(status, { error: { code, message: code, details } })

function memoryStorage(): TokenStorage {
  const data = new Map<string, string>()
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => void data.set(key, value),
    removeItem: (key) => void data.delete(key),
  }
}

/** Renders routes with real providers and an in-memory API keyed by "METHOD /path". */
export function renderWithApi(
  routes: RouteObject[],
  api: Record<string, Route>,
  initialEntry: string,
) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input))
    const key = `${(init.method ?? 'GET').toUpperCase()} ${url.pathname}`
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : undefined
    const handler = api[key]
    return handler ? handler(body, url) : apiError(404, 'NOT_FOUND')
  })
  const client = createApiClient({
    baseUrl: 'http://api.test',
    tokens: new TokenStore(memoryStorage()),
    fetch: fetchMock as unknown as typeof fetch,
  })
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter(routes, { initialEntries: [initialEntry] })
  const view = render(
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={client}>
        <ToastProvider closeLabel="Yopish" regionLabel="Bildirishnomalar">
          <RouterProvider router={router} />
        </ToastProvider>
      </ApiProvider>
    </QueryClientProvider>,
  )
  return { ...view, fetchMock, router, client }
}
