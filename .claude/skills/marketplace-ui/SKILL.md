---
name: marketplace-ui
description: Use when building or changing any UI in frontend/ — the Bozorcha design system (brand, tokens, typography, components, status colors, UX rules).
---

# Bozorcha design system

Load together with `frontend-design:frontend-design`. Where they conflict, this file wins (it is the brand).

## Brand
- Name: **Bozorcha** ("little bazaar") — short, Uzbek, friendly. Wordmark: lowercase `bozorcha`, heading font, weight 800, primary color; the dot of an optional "o" accent may use the accent color.
- Voice: clean, trustworthy, modern. Uzbek (Latin) UI copy, short verbs on buttons ("Savatchaga", "Rasmiylashtirish").
- Avoid the generic "AI template" look: no purple gradients, no glassmorphism, no emoji icons, no giant centered hero with stock blobs. Prefer dense, useful commerce layouts (think well-made local marketplace), real hierarchy, generous but deliberate whitespace.

## Color tokens
Defined as CSS variables in `packages/ui/src/styles/tokens.css` and mapped into Tailwind v4 via `@theme`. Never hardcode hex in components.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--color-primary` | `#0F6E56` | `#34B08E` | brand, links, primary buttons |
| `--color-primary-hover` | `#0B5A46` | `#4CC4A2` | |
| `--color-primary-soft` | `#E3F2EC` | `#123B31` | selected chips, subtle fills |
| `--color-accent` | `#EF9F27` | `#F4B04A` | prices, discounts, key CTA ("Savatchaga") |
| `--color-accent-fg` | `#2B1A00` | `#2B1A00` | text on accent |
| `--color-bg` | `#FAF8F5` | `#151412` | page |
| `--color-surface` | `#FFFFFF` | `#1E1C1A` | cards |
| `--color-surface-2` | `#F3F0EB` | `#262422` | inputs, table stripes |
| `--color-border` | `#E4DFD7` | `#37332F` | |
| `--color-text` | `#1F1C18` | `#F2EFEA` | |
| `--color-text-muted` | `#6B645B` | `#A59E94` | |
| `--color-danger` | `#C63D2F` | `#F0715F` | |
| `--color-success` | `#1E8A4C` | `#4CC27F` | |
| `--color-info` | `#2F6FB5` | `#6FA6E6` | |
| `--color-purple` | `#6B4BC4` | `#A58BF0` | shipped |

Derived tokens keep every text pair at WCAG AA (defined next to the brand values in `packages/ui/src/styles/tokens.css`):
- `--color-accent-ink` (`#8A5100` light / `#F4B04A` dark) — price and accent **text**. The brand amber on white is only 2.2:1, so never use `--color-accent` for text.
- `--color-primary-fg` (`#FFFFFF` light / `#10201B` dark) — text on primary buttons; white on the dark-mode primary is only 2.7:1.
- `--color-{danger,success,info,purple}-ink` for status text and `-soft` for status backgrounds (badges, alerts); `--color-accent-soft` for discount chips.

Neutrals are a warm gray scale. Dark mode is mandatory: `class="dark"` on `<html>`, toggle persisted, defaults to system. All text/background pairs meet WCAG AA.

## Typography
- UI: **Inter**; headings: **Manrope** (700/800). Installed via `@fontsource/inter`, `@fontsource/manrope` — no CDN.
- Scale (px): 12, 14 (body-sm), 16 (body), 18, 20, 24, 30, 36. Line-height 1.5 body, 1.2 headings.
- Numbers, prices, timers, tables: `font-variant-numeric: tabular-nums`.

## Layout & shape
- 4px spacing grid (Tailwind default scale). Page gutter 16px mobile, 24px tablet, max content width 1280px.
- Cards `rounded-xl`, buttons/inputs `rounded-lg`, chips `rounded-full`.
- One soft shadow level: `0 1px 2px rgb(0 0 0 / .06), 0 2px 8px rgb(0 0 0 / .04)`; dark mode uses borders instead of shadows.
- Transitions 150–200ms ease-out on color/opacity/transform only. Respect `prefers-reduced-motion`.
- Mobile-first; at 360px there is never horizontal scroll. Filters move into a Drawer below `lg`.

## Components (`packages/ui`)
Button (primary / secondary / ghost / danger; sizes sm/md/lg; `loading` shows spinner and keeps width), Input, Select, Checkbox, RangeSlider, Badge, Card, ProductCard, PriceTag (current price in accent, old price struck-through muted, discount % badge), QtyStepper (1..99), Tabs, Dialog, Drawer, Toast, Skeleton, EmptyState (icon + title + action), DataTable, Stepper/Timeline, CountdownTimer (mm:ss, turns danger under 2 min), OtpInput (6 cells, auto-advance, paste support), ImageUploader (drag & drop, progress, `processing` state).

Every component: keyboard operable, visible focus ring (`2px` primary outline, offset 2), proper `aria-*`, forwards `className` and `ref`.

## Order status colors (shop and seller identical)
| Status | Badge |
|---|---|
| PENDING | gray |
| RESERVED | info (blue) |
| PAID | success (green) |
| ACCEPTED / FULFILLING | info |
| SHIPPED | purple |
| DELIVERED / COMPLETED | primary (dark green) |
| CANCELLED / CANCELLED_BY_SELLER / REFUNDED | danger (red) |
| EXPIRED | gray, muted |

## UX rules
- Prices come as integer tiyin; format with `Intl.NumberFormat('uz-UZ')` + ` so'm` → `1 250 000 so'm`.
- Every page/section has a loading skeleton, an empty state and an error state with retry.
- Icons: `lucide-react`, 20px, stroke 1.75.
- i18n: all strings via keys, `uz` default locale.
- Screenshot each main page at 360px and 1280px, light and dark, into the directory your task names.
