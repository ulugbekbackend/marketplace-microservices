import { vi } from 'vitest'

export type FakeRequest = {
  method: string
  url: URL
  headers: Record<string, string>
  body: unknown
}

export type Handler = (req: FakeRequest) => Response | Promise<Response>

export const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

export const errorBody = (code: string, message = code, details?: unknown) => ({
  error: { code, message, details },
})

/** A controllable promise, used to hold a response until the test releases it. */
export function deferred<T = void>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

/** In-memory fetch: routes by "METHOD /path", records every call. */
export function fakeFetch(routes: Record<string, Handler>) {
  const calls: FakeRequest[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input))
    const method = (init.method ?? 'GET').toUpperCase()
    const headers = { ...(init.headers as Record<string, string>) }
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : undefined
    const req = { method, url, headers, body }
    calls.push(req)
    const handler = routes[`${method} ${url.pathname}`]
    if (!handler) return json(404, errorBody('NOT_FOUND'))
    return handler(req)
  })
  const callsTo = (method: string, path: string) =>
    calls.filter((c) => c.method === method && c.url.pathname === path)
  return { fetch: fetchMock as unknown as typeof fetch, calls, callsTo }
}

/** A Storage-like map for TokenStore tests. */
export function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial))
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
    data,
  }
}
