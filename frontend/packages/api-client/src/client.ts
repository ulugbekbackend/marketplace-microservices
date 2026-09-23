import { ApiError, CLIENT_ERROR, parseErrorResponse } from './errors'
import { IDEMPOTENCY_HEADER } from './idempotency'
import { TokenStore } from './tokens'
import type { TokenRefreshResponse } from './types'

export const DEFAULT_API_URL = 'http://api.localhost'

export const REFRESH_PATH = '/api/auth/token/refresh/'

/** Endpoints that must never trigger a token refresh on 401. */
const NO_REFRESH_PATHS = [REFRESH_PATH, '/api/auth/otp/send/', '/api/auth/otp/verify/']

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export type QueryValue = string | number | boolean | null | undefined
export type Query = Record<string, QueryValue>

export type RequestOptions = {
  query?: Query
  body?: unknown
  headers?: Record<string, string>
  /** Sent as the `Idempotency-Key` header (see `newIdempotencyKey`). */
  idempotencyKey?: string
  signal?: AbortSignal
}

export type ApiClientOptions = {
  baseUrl?: string
  tokens?: TokenStore
  fetch?: typeof fetch
  /** Called after the session ends because the refresh token was rejected. */
  onSessionExpired?: () => void
}

export type ApiClient = {
  readonly baseUrl: string
  readonly tokens: TokenStore
  request<T>(method: HttpMethod, path: string, options?: RequestOptions): Promise<T>
  get<T>(path: string, options?: Omit<RequestOptions, 'body'>): Promise<T>
  post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T>
  patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T>
  delete<T>(path: string, options?: RequestOptions): Promise<T>
  /** Rotates tokens once; concurrent callers share the same in-flight refresh. */
  refresh(): Promise<boolean>
}

export function buildUrl(baseUrl: string, path: string, query?: Query): string {
  const url = new URL(path, baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`)
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === '') continue
      url.searchParams.set(key, String(value))
    }
  }
  return url.toString()
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const baseUrl = options.baseUrl || DEFAULT_API_URL
  const tokens = options.tokens ?? new TokenStore()
  const fetchImpl = options.fetch ?? ((...args: Parameters<typeof fetch>) => fetch(...args))
  let inflightRefresh: Promise<boolean> | null = null

  async function rawFetch(
    method: HttpMethod,
    path: string,
    opts: RequestOptions,
    accessToken: string | null,
  ): Promise<Response> {
    const headers: Record<string, string> = { Accept: 'application/json', ...opts.headers }
    if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`
    if (opts.idempotencyKey) headers[IDEMPOTENCY_HEADER] = opts.idempotencyKey
    try {
      return await fetchImpl(buildUrl(baseUrl, path, opts.query), {
        method,
        headers,
        body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
        signal: opts.signal,
      })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new ApiError(0, CLIENT_ERROR.ABORTED, 'Request was aborted')
      }
      throw new ApiError(0, CLIENT_ERROR.NETWORK, 'Network request failed', error)
    }
  }

  async function doRefresh(): Promise<boolean> {
    const refreshToken = tokens.getRefresh()
    if (!refreshToken) return false
    const response = await rawFetch('POST', REFRESH_PATH, { body: { refresh: refreshToken } }, null)
    if (!response.ok) {
      // The refresh token is invalid, expired or already rotated: the session is over.
      if (response.status >= 400 && response.status < 500) {
        tokens.clear()
        options.onSessionExpired?.()
        return false
      }
      throw await parseErrorResponse(response)
    }
    const data = (await response.json()) as TokenRefreshResponse
    tokens.set({ access: data.access, refresh: data.refresh })
    return true
  }

  function refresh(): Promise<boolean> {
    inflightRefresh ??= doRefresh().finally(() => {
      inflightRefresh = null
    })
    return inflightRefresh
  }

  async function parseBody<T>(response: Response): Promise<T> {
    if (response.status === 204 || response.status === 205) return undefined as T
    const text = await response.text()
    if (!text) return undefined as T
    try {
      return JSON.parse(text) as T
    } catch (error) {
      throw new ApiError(
        response.status,
        CLIENT_ERROR.INVALID_RESPONSE,
        'Response is not valid JSON',
        error,
      )
    }
  }

  async function request<T>(
    method: HttpMethod,
    path: string,
    opts: RequestOptions = {},
  ): Promise<T> {
    // A refresh already in flight (another request got a 401): wait instead of sending a
    // request that is bound to fail with the old token.
    if (inflightRefresh) await inflightRefresh.catch(() => false)

    const usedToken = tokens.getAccess()
    let response = await rawFetch(method, path, opts, usedToken)

    if (response.status === 401 && !NO_REFRESH_PATHS.includes(path) && tokens.getRefresh()) {
      // If the token changed while this request was in flight, another request already
      // refreshed: just retry with the new one.
      const refreshed = tokens.getAccess() !== usedToken || (await refresh())
      if (refreshed) {
        response = await rawFetch(method, path, opts, tokens.getAccess())
      }
    }

    if (!response.ok) throw await parseErrorResponse(response)
    return parseBody<T>(response)
  }

  return {
    baseUrl,
    tokens,
    request,
    refresh,
    get: (path, opts) => request('GET', path, opts),
    post: (path, body, opts) => request('POST', path, { ...opts, body }),
    patch: (path, body, opts) => request('PATCH', path, { ...opts, body }),
    delete: (path, opts) => request('DELETE', path, opts),
  }
}
