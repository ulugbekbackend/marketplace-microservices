import type { Category } from '@bozorcha/api-client'

/** Ancestors of the category with `slug`, root first, including the category itself. */
export function findCategoryPath(tree: Category[], slug: string): Category[] {
  for (const node of tree) {
    if (node.slug === slug) return [node]
    const path = findCategoryPath(node.children, slug)
    if (path.length > 0) return [node, ...path]
  }
  return []
}
