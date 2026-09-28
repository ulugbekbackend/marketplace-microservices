import type { LinkLikeProps } from '@bozorcha/ui'
import { Link } from 'react-router'

/** Adapter so router-agnostic UI components (ProductCard, Pagination) navigate client-side. */
export function RouterLink({ href, className, children }: LinkLikeProps) {
  return (
    <Link to={href} className={className}>
      {children}
    </Link>
  )
}
