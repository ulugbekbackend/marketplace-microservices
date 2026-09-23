import { describe, expect, it, vi } from 'vitest'
import { buildUrl, createApiClient, REFRESH_PATH } from '../src/client'
import { authEndpoints } from '../src/endpoints'
import { ApiError, CLIENT_ERROR, shouldRetry } from '../src/errors'
import { IDEMPOTENCY_HEADER, newIdempotencyKey } from '../src/idempotency'
import { REFRESH_TOKEN_KEY, TokenStore } from '../src/tokens'
import { deferred, errorBody, fakeFetch, json, memoryStorage, type FakeRequest } from './fakeServer'

const BASE = 'http://api.test'
const ME = '/api/auth/me/'

/** Protected endpoint: 200 only with the given access token. */
const protectedRoute = (validToken: () => string) => (req: FakeRequest) =>
  req.headers.Authorization === `Bearer ${validToken()}`
    ? json(200, { id: 'u1', path: req.url.pathname })
    : json(401, errorBody('TOKEN_INVALID', 'Token is invalid or expired'))

function setup(
  routes: Parameters<typeof fakeFetch>[0],
  opts: { refresh?: string | null; access?: string } = {},
) {
  const storage = memoryStorage(
    opts.refresh === null ? {} : { [REFRESH_TOKEN_KEY]: opts.refresh ?? 'r1' },
  )
  const tokens = new TokenStore(storage)
  if (opts.access) tokens.set({ access: opts.access, refresh: opts.refresh ?? 'r1' })
  const server = fakeFetch(routes)
  const onSessionExpired = vi.fn()
  const client = createApiClient({ baseUrl: BASE, tokens, fetch: server.fetch, onSessionExpired })
  return { client, tokens, storage, server, onSessionExpired }
}

describe('request basics', () => {
  it('builds URLs, skipping empty query values', () => {
    expect(
      buildUrl(BASE, '/api/catalog/products/', {
        category: 'kiyim',
        seller: undefined,
        q: '',
        page: 2,
      }),
    ).toBe(`${BASE}/api/catalog/products/?category=kiyim&page=2`)
    expect(buildUrl(`${BASE}/`, '/api/x/')).toBe(`${BASE}/api/x/`)
  })

  it('sends JSON with the bearer token and parses the response', async () => {
    const { client, server } = setup(
      { [`GET ${ME}`]: protectedRoute(() => 'a1') },
      { access: 'a1' },
    )
    await expect(client.get(ME)).resolves.toEqual({ id: 'u1', path: ME })
    expect(server.calls[0]!.headers.Authorization).toBe('Bearer a1')
    expect(server.calls[0]!.headers.Accept).toBe('application/json')
  })

  it('omits Authorization without an access token and returns undefined for 204', async () => {
    const { client, server } = setup(
      { 'POST /api/auth/otp/send/': () => new Response(null, { status: 204 }) },
      { refresh: null },
    )
    await expect(
      client.post('/api/auth/otp/send/', { phone: '+998901234567' }),
    ).resolves.toBeUndefined()
    expect(server.calls[0]!.headers.Authorization).toBeUndefined()
    expect(server.calls[0]!.headers['Content-Type']).toBe('application/json')
    expect(server.calls[0]!.body).toEqual({ phone: '+998901234567' })
  })

  it('adds the Idempotency-Key header when requested', async () => {
    const { client, server } = setup({ 'POST /api/orders/': () => json(201, { id: 'o1' }) })
    const key = newIdempotencyKey()
    await client.post('/api/orders/', {}, { idempotencyKey: key })
    expect(server.calls[0]!.headers[IDEMPOTENCY_HEADER]).toBe(key)
  })
})

describe('token refresh on 401', () => {
  it('refreshes once, stores the rotated tokens and retries the request', async () => {
    let valid = 'a2'
    const { client, tokens, storage, server } = setup(
      {
        [`GET ${ME}`]: protectedRoute(() => valid),
        [`POST ${REFRESH_PATH}`]: (req) => {
          expect(req.body).toEqual({ refresh: 'r1' })
          valid = 'a2'
          return json(200, { access: 'a2', refresh: 'r2' })
        },
      },
      { access: 'expired' },
    )
    await expect(client.get(ME)).resolves.toMatchObject({ id: 'u1' })
    expect(server.callsTo('POST', REFRESH_PATH)).toHaveLength(1)
    expect(server.callsTo('GET', ME).map((c) => c.headers.Authorization)).toEqual([
      'Bearer expired',
      'Bearer a2',
    ])
    expect(tokens.getAccess()).toBe('a2')
    expect(storage.data.get(REFRESH_TOKEN_KEY)).toBe('r2')
  })

  it('restores a session after reload (no access token yet) through the refresh token', async () => {
    const { client, server } = setup({
      [`GET ${ME}`]: protectedRoute(() => 'fresh'),
      [`POST ${REFRESH_PATH}`]: () => json(200, { access: 'fresh', refresh: 'r2' }),
    })
    await expect(client.get(ME)).resolves.toMatchObject({ id: 'u1' })
    expect(server.callsTo('POST', REFRESH_PATH)).toHaveLength(1)
  })

  it('concurrent 401s share a single refresh', async () => {
    const gate = deferred()
    const { client, server } = setup(
      {
        'GET /api/a/': protectedRoute(() => 'a2'),
        'GET /api/b/': protectedRoute(() => 'a2'),
        'GET /api/c/': protectedRoute(() => 'a2'),
        [`POST ${REFRESH_PATH}`]: async () => {
          await gate.promise
          return json(200, { access: 'a2', refresh: 'r2' })
        },
      },
      { access: 'expired' },
    )
    const pending = Promise.all([
      client.get('/api/a/'),
      client.get('/api/b/'),
      client.get('/api/c/'),
    ])
    await vi.waitFor(() => expect(server.callsTo('POST', REFRESH_PATH)).toHaveLength(1))
    // a request issued while the refresh is in flight waits for it instead of failing
    const late = client.get('/api/a/')
    gate.resolve()
    await expect(pending).resolves.toHaveLength(3)
    await expect(late).resolves.toMatchObject({ id: 'u1' })
    expect(server.callsTo('POST', REFRESH_PATH)).toHaveLength(1)
    const retried = server.calls.filter((c) => c.headers.Authorization === 'Bearer a2')
    expect(retried).toHaveLength(4)
  })

  it('a 401 that arrives after another request already refreshed just retries', async () => {
    const slow = deferred()
    let valid = 'expired'
    const { client, server } = setup(
      {
        'GET /api/fast/': protectedRoute(() => valid),
        'GET /api/slow/': async (req) => {
          const seenToken = req.headers.Authorization
          await slow.promise
          return seenToken === `Bearer ${valid}`
            ? json(200, { ok: 1 })
            : json(401, errorBody('TOKEN_INVALID'))
        },
        [`POST ${REFRESH_PATH}`]: () => {
          valid = 'a2'
          return json(200, { access: 'a2', refresh: 'r2' })
        },
      },
      { access: 'old' },
    )
    const slowRequest = client.get('/api/slow/')
    await client.get('/api/fast/') // 401 -> refresh -> retry OK
    slow.resolve() // the slow one now fails with the old token
    await expect(slowRequest).resolves.toEqual({ ok: 1 })
    expect(server.callsTo('POST', REFRESH_PATH)).toHaveLength(1)
  })

  it('refresh failure ends the session: tokens cleared, callback fired, original 401 thrown', async () => {
    const { client, tokens, storage, server, onSessionExpired } = setup(
      {
        'GET /api/a/': protectedRoute(() => 'never'),
        'GET /api/b/': protectedRoute(() => 'never'),
        [`POST ${REFRESH_PATH}`]: () =>
          json(401, errorBody('TOKEN_INVALID', 'Refresh token revoked')),
      },
      { access: 'expired' },
    )
    const results = await Promise.allSettled([client.get('/api/a/'), client.get('/api/b/')])
    for (const result of results) {
      expect(result.status).toBe('rejected')
      const error = (result as PromiseRejectedResult).reason as ApiError
      expect(error).toBeInstanceOf(ApiError)
      expect(error.status).toBe(401)
      expect(error.code).toBe('TOKEN_INVALID')
    }
    expect(server.callsTo('POST', REFRESH_PATH)).toHaveLength(1)
    expect(onSessionExpired).toHaveBeenCalledOnce()
    expect(tokens.getAccess()).toBeNull()
    expect(storage.data.has(REFRESH_TOKEN_KEY)).toBe(false)
    expect(tokens.getSnapshot().hasSession).toBe(false)
  })

  it('a 5xx from the refresh endpoint keeps the session (transient failure)', async () => {
    const { client, tokens, onSessionExpired } = setup(
      {
        [`GET ${ME}`]: protectedRoute(() => 'never'),
        [`POST ${REFRESH_PATH}`]: () => json(503, errorBody('UNAVAILABLE', 'Try later')),
      },
      { access: 'expired' },
    )
    await expect(client.get(ME)).rejects.toMatchObject({ status: 503, code: 'UNAVAILABLE' })
    expect(onSessionExpired).not.toHaveBeenCalled()
    expect(tokens.getRefresh()).toBe('r1')
  })

  it('does not refresh without a refresh token or for auth endpoints', async () => {
    const anonymous = setup({ [`GET ${ME}`]: protectedRoute(() => 'x') }, { refresh: null })
    await expect(anonymous.client.get(ME)).rejects.toMatchObject({ status: 401 })
    expect(anonymous.server.callsTo('POST', REFRESH_PATH)).toHaveLength(0)

    const verify = setup({
      'POST /api/auth/otp/verify/': () => json(401, errorBody('OTP_INVALID', 'Wrong code')),
    })
    await expect(verify.client.post('/api/auth/otp/verify/', {})).rejects.toMatchObject({
      code: 'OTP_INVALID',
    })
    expect(verify.server.callsTo('POST', REFRESH_PATH)).toHaveLength(0)
  })
})

describe('error parsing', () => {
  it('parses the shared error shape into a typed ApiError', async () => {
    const { client } = setup({
      'POST /api/auth/otp/verify/': () =>
        json(400, errorBody('OTP_EXPIRED', 'Code expired', { attempts_left: 2 })),
    })
    const error = await client.post('/api/auth/otp/verify/', {}).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 400,
      code: 'OTP_EXPIRED',
      message: 'Code expired',
      details: { attempts_left: 2 },
      isClientError: true,
    })
  })

  it('falls back for DRF detail, plain text and empty bodies', async () => {
    const { client } = setup({
      'GET /api/drf/': () => json(403, { detail: 'Forbidden here' }),
      'GET /api/text/': () =>
        new Response('Bad Gateway', { status: 502, statusText: 'Bad Gateway' }),
      'GET /api/empty/': () => new Response(null, { status: 500, statusText: 'Server Error' }),
    })
    await expect(client.get('/api/drf/')).rejects.toMatchObject({
      status: 403,
      code: 'HTTP_403',
      message: 'Forbidden here',
    })
    await expect(client.get('/api/text/')).rejects.toMatchObject({
      status: 502,
      code: 'HTTP_502',
      details: 'Bad Gateway',
    })
    await expect(client.get('/api/empty/')).rejects.toMatchObject({
      status: 500,
      message: 'Server Error',
    })
  })

  it('maps network failures and aborts', async () => {
    const tokens = new TokenStore(memoryStorage())
    const failing = createApiClient({
      baseUrl: BASE,
      tokens,
      fetch: () => Promise.reject(new TypeError('Failed to fetch')),
    })
    await expect(failing.get('/api/x/')).rejects.toMatchObject({
      status: 0,
      code: CLIENT_ERROR.NETWORK,
    })

    const aborting = createApiClient({
      baseUrl: BASE,
      tokens,
      fetch: () => Promise.reject(new DOMException('aborted', 'AbortError')),
    })
    await expect(aborting.get('/api/x/')).rejects.toMatchObject({ code: CLIENT_ERROR.ABORTED })
  })

  it('reports invalid JSON', async () => {
    const { client } = setup({ 'GET /api/bad/': () => new Response('{nope', { status: 200 }) })
    await expect(client.get('/api/bad/')).rejects.toMatchObject({
      code: CLIENT_ERROR.INVALID_RESPONSE,
    })
  })

  it('retry policy skips client errors', () => {
    expect(shouldRetry(0, new ApiError(404, 'NOT_FOUND', 'x'))).toBe(false)
    expect(shouldRetry(0, new ApiError(0, CLIENT_ERROR.NETWORK, 'x'))).toBe(true)
    expect(shouldRetry(2, new ApiError(503, 'X', 'x'))).toBe(false)
  })
})

describe('auth endpoints and token store', () => {
  it('verifyOtp stores tokens; logout revokes and clears even when the server fails', async () => {
    const { client, tokens, storage, server } = setup(
      {
        'POST /api/auth/otp/verify/': () =>
          json(200, {
            access: 'a1',
            refresh: 'r9',
            user: { id: 'u1', phone: '+998901234567', full_name: '', role: 'customer' },
          }),
        'POST /api/auth/logout/': () => json(500, errorBody('BOOM')),
      },
      { refresh: null },
    )
    const auth = authEndpoints(client)
    const result = await auth.verifyOtp('+998901234567', '123456')
    expect(result.user.role).toBe('customer')
    expect(tokens.getAccess()).toBe('a1')
    expect(storage.data.get(REFRESH_TOKEN_KEY)).toBe('r9')
    expect(tokens.getSnapshot().hasSession).toBe(true)

    await expect(auth.logout()).rejects.toMatchObject({ code: 'BOOM' })
    expect(server.callsTo('POST', '/api/auth/logout/')[0]!.body).toEqual({ refresh: 'r9' })
    expect(tokens.getAccess()).toBeNull()
    expect(storage.data.size).toBe(0)
  })

  it('keeps the access token in memory only and notifies subscribers', () => {
    const storage = memoryStorage()
    const tokens = new TokenStore(storage)
    const listener = vi.fn()
    tokens.subscribe(listener)
    const before = tokens.getSnapshot()
    tokens.set({ access: 'secret-access', refresh: 'r1' })
    expect([...storage.data.values()]).toEqual(['r1'])
    expect(listener).toHaveBeenCalledOnce()
    expect(tokens.getSnapshot()).not.toBe(before)
    expect(tokens.getSnapshot().hasSession).toBe(true)
  })

  it('generates v4 UUID idempotency keys, also without randomUUID', () => {
    const uuidV4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
    expect(newIdempotencyKey()).toMatch(uuidV4)
    // simulate a non-secure context where crypto.randomUUID is missing
    const target = Object.hasOwn(crypto, 'randomUUID') ? crypto : Object.getPrototypeOf(crypto)
    const original = Object.getOwnPropertyDescriptor(target, 'randomUUID')!
    Object.defineProperty(target, 'randomUUID', { value: undefined, configurable: true })
    try {
      const a = newIdempotencyKey()
      expect(a).toMatch(uuidV4)
      expect(newIdempotencyKey()).not.toBe(a)
    } finally {
      Object.defineProperty(target, 'randomUUID', original)
    }
    expect(typeof crypto.randomUUID).toBe('function')
  })
})
