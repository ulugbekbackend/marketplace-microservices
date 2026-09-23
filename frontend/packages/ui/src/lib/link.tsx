import type { ComponentType, ReactNode } from 'react'

export type LinkLikeProps = { href: string; className?: string; children: ReactNode }

/**
 * Components that render navigation accept a `linkAs` adapter so the UI package stays
 * router-agnostic (the app passes a wrapper around its router's Link).
 */
export type LinkComponent = ComponentType<LinkLikeProps>

export function DefaultLink({ href, className, children }: LinkLikeProps) {
  return (
    <a href={href} className={className}>
      {children}
    </a>
  )
}
