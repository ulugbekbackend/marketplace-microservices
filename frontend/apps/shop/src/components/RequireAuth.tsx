import { useSession } from '@bozorcha/api-client'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'

/** Guests are sent to login and brought back to this page afterwards. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useSession()
  const location = useLocation()
  if (!isAuthenticated) {
    const next = encodeURIComponent(`${location.pathname}${location.search}`)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  return children
}
