import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { createApiClient } from '../src/client'
import { useLogout, useMe, useVerifyOtp } from '../src/hooks/auth'
import { useProducts } from '../src/hooks/catalog'
import { ApiProvider, useSession } from '../src/hooks/context'
import { queryKeys } from '../src/hooks/keys'
import { TokenStore } from '../src/tokens'
import { fakeFetch, json, memoryStorage } from './fakeServer'

const user = { id: 'u1', phone: '+998901234567', full_name: 'Aziza', role: 'customer' as const }

function setup() {
  const server = fakeFetch({
    'POST /api/auth/otp/verify/': () => json(200, { access: 'a1', refresh: 'r1', user }),
    'GET /api/auth/me/': () => json(200, user),
    'POST /api/auth/logout/': () => new Response(null, { status: 204 }),
    'GET /api/catalog/products/': (req) =>
      json(200, {
        items: [],
        total: 0,
        page: Number(req.url.searchParams.get('page') ?? 1),
        page_size: 24,
      }),
  })
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
  return { server, client, queryClient, wrapper }
}

describe('auth hooks', () => {
  it('login flips the session, seeds the user cache; logout clears both', async () => {
    const { wrapper, queryClient, server } = setup()
    const { result } = renderHook(
      () => ({ session: useSession(), me: useMe(), verify: useVerifyOtp(), logout: useLogout() }),
      { wrapper },
    )
    expect(result.current.session.isAuthenticated).toBe(false)
    expect(result.current.me.fetchStatus).toBe('idle')

    await act(() => result.current.verify.mutateAsync({ phone: user.phone, code: '123456' }))
    expect(result.current.session.isAuthenticated).toBe(true)
    expect(queryClient.getQueryData(queryKeys.me)).toEqual(user)
    await waitFor(() => expect(result.current.me.data).toEqual(user))

    await act(() => result.current.logout.mutateAsync())
    expect(result.current.session.isAuthenticated).toBe(false)
    expect(queryClient.getQueryData(queryKeys.me)).toBeUndefined()
    expect(server.callsTo('POST', '/api/auth/logout/')).toHaveLength(1)
  })
})

describe('catalog hooks', () => {
  it('passes list params as query string', async () => {
    const { wrapper, server } = setup()
    const { result } = renderHook(
      () => useProducts({ category: 'kiyim', page: 2, page_size: 24 }),
      {
        wrapper,
      },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.page).toBe(2)
    const url = server.callsTo('GET', '/api/catalog/products/')[0]!.url
    expect(Object.fromEntries(url.searchParams)).toEqual({
      category: 'kiyim',
      page: '2',
      page_size: '24',
    })
  })
})
