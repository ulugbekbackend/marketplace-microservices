import { createContext, useContext, useMemo, useSyncExternalStore, type ReactNode } from 'react'
import type { ApiClient } from '../client'
import {
  authEndpoints,
  cartEndpoints,
  catalogEndpoints,
  orderEndpoints,
  paymentEndpoints,
  searchEndpoints,
  sellerCatalogEndpoints,
  sellerOrderEndpoints,
} from '../endpoints'

type ApiContextValue = {
  client: ApiClient
  auth: ReturnType<typeof authEndpoints>
  catalog: ReturnType<typeof catalogEndpoints>
  cart: ReturnType<typeof cartEndpoints>
  orders: ReturnType<typeof orderEndpoints>
  payments: ReturnType<typeof paymentEndpoints>
  search: ReturnType<typeof searchEndpoints>
  seller: ReturnType<typeof sellerCatalogEndpoints>
  sellerOrders: ReturnType<typeof sellerOrderEndpoints>
}

const ApiContext = createContext<ApiContextValue | null>(null)

export function ApiProvider({ client, children }: { client: ApiClient; children: ReactNode }) {
  const value = useMemo(
    () => ({
      client,
      auth: authEndpoints(client),
      catalog: catalogEndpoints(client),
      cart: cartEndpoints(client),
      orders: orderEndpoints(client),
      payments: paymentEndpoints(client),
      search: searchEndpoints(client),
      seller: sellerCatalogEndpoints(client),
      sellerOrders: sellerOrderEndpoints(client),
    }),
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
