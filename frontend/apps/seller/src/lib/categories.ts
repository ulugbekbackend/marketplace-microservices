import type { Category } from '@bozorcha/api-client'

export type CategoryOption = { id: string; name: string; depth: number; path: string }

/** Depth-first list of the category tree, for an indented select. */
export function flattenCategories(tree: readonly Category[], depth = 0, parents: string[] = []) {
  const options: CategoryOption[] = []
  for (const node of tree) {
    const trail = [...parents, node.name]
    options.push({ id: node.id, name: node.name, depth, path: trail.join(' / ') })
    options.push(...flattenCategories(node.children, depth + 1, trail))
  }
  return options
}

/** Three non-breaking spaces per level: `<option>` ignores CSS padding and trims normal spaces. */
const INDENT = String.fromCharCode(0xa0).repeat(3)

export const indentedLabel = (option: CategoryOption) =>
  `${INDENT.repeat(option.depth)}${option.name}`
