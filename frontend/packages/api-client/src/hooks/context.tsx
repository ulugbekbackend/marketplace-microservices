import { createContext, useContext, useMemo, useSyncExternalStore, type ReactNode } from 'react'
import type { ApiClient } from '../client'
import { authEndpoints, catalogEndpoints } from '../endpoints'

type ApiContextValue = {
  client: ApiClient
  auth: ReturnType<typeof authEndpoints>
  catalog: ReturnType<typeof catalogEndpoints>
}

const ApiContext = createContext<ApiContextValue | null>(null)

export function ApiProvider({ client, children }: { client: ApiClient; children: ReactNode }) {
  const value = useMemo(
    () => ({ client, auth: authEndpoints(client), catalog: catalogEndpoints(client) }),
    [client],
  )
  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>
}

export function useApi(): ApiContextValue {
  const value = useContext(ApiContext)
  if (!value) throw new Error('useApi must be used inside <ApiProvider>')
  return value
}

/** Re-renders when the user signs in or out (including a rejected refresh token). */
export function useSession(): { isAuthenticated: boolean } {
  const { client } = useApi()
  const snapshot = useSyncExternalStore(client.tokens.subscribe, client.tokens.getSnapshot)
  return { isAuthenticated: snapshot.hasSession }
}
