import { createElement } from 'react'
import {
  Apple,
  Baby,
  BookOpen,
  Car,
  Dumbbell,
  Gem,
  Hammer,
  Laptop,
  type LucideIcon,
  Package,
  PawPrint,
  Shirt,
  Smartphone,
  Sofa,
  Sparkles,
  Tv,
  UtensilsCrossed,
} from 'lucide-react'

// Matched against the category slug; first hit wins. Unknown categories get a neutral box.
const RULES: Array<[RegExp, LucideIcon]> = [
  [/telefon|smartfon|phone/, Smartphone],
  [/noutbuk|kompyuter|laptop|computer/, Laptop],
  [/elektron|maishiy-texnika|televizor|tv/, Tv],
  [/kiyim|poyabzal|fashion|clothes|shoes/, Shirt],
  [/zargarlik|aksessuar|jewel|accessor/, Gem],
  [/uy|mebel|interyer|home|furniture/, Sofa],
  [/oshxona|idish|kitchen/, UtensilsCrossed],
  [/gozallik|go-zallik|kosmetika|beauty|parfyum/, Sparkles],
  [/bolalar|oyinchoq|kids|toys|baby/, Baby],
  [/sport|fitnes|outdoor/, Dumbbell],
  [/kitob|kanstovar|book/, BookOpen],
  [/oziq|ovqat|food|grocery|meva/, Apple],
  [/avto|mashina|auto|car/, Car],
  [/qurilish|asbob|tools|garden|bog/, Hammer],
  [/hayvon|pet/, PawPrint],
]

function categoryIcon(slug: string): LucideIcon {
  return RULES.find(([pattern]) => pattern.test(slug))?.[1] ?? Package
}

/** Icon for a category slug (static lookup, safe to render). */
export function CategoryIcon({ slug, size = 20 }: { slug: string; size?: number }) {
  return createElement(categoryIcon(slug), { 'aria-hidden': true, size, strokeWidth: 1.75 })
}
