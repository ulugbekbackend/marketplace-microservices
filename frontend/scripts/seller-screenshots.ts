/**
 * Screenshots of the seller panel with a mocked API (Playwright route interception).
 *
 *   pnpm --filter seller build
 *   pnpm screenshots:seller <output-dir> [--url http://localhost:4180]
 *
 * Without --url the script serves the built app with `vite preview` itself. Every page is shot at
 * 360px and 1280px in light and dark mode. The run fails if a page scrolls horizontally, an
 * element sticks out of the viewport, or the page logs errors.
 */
import { spawn, type ChildProcess } from 'node:child_process'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium, type Page, type Route } from '@playwright/test'
import { IMAGE_HOST, productSvg } from './fixtures'

const PREVIEW_PORT = 4180
const WIDTHS = [360, 1280] as const
const THEMES = ['light', 'dark'] as const

type Role = 'seller' | 'customer'
type Shot = {
  name: string
  path: string
  /** Signed-in role; guests when omitted. */
  role?: Role
  application?: 'approved' | 'pending' | 'none'
  emptyProducts?: boolean
  prepare?: (page: Page) => Promise<void>
}

const img = (i: number) => `${IMAGE_HOST}/p/${i}.svg`
const at = (daysAgo: number) => new Date(Date.UTC(2026, 8, 27 - daysAgo, 9, 30)).toISOString()

const attributes = [
  {
    id: 'a-rang',
    code: 'color',
    name: 'Rang',
    values: [
      { id: 'v-qizil', value: 'Qizil' },
      { id: 'v-kok', value: "Ko'k" },
      { id: 'v-yashil', value: 'Yashil' },
      { id: 'v-oq', value: 'Oq' },
    ],
  },
  {
    id: 'a-olcham',
    code: 'size',
    name: "O'lcham",
    values: ['S', 'M', 'L', 'XL'].map((value) => ({ id: `v-${value}`, value })),
  },
  {
    id: 'a-hajm',
    code: 'volume',
    name: 'Hajm',
    values: ['0,5 l', '1 l', '1,5 l'].map((value, i) => ({ id: `v-h${i}`, value })),
  },
]

const categories = [
  {
    id: 'c-kiyim',
    name: 'Kiyim va poyabzal',
    slug: 'kiyim',
    children: [
      { id: 'c-ayollar', name: 'Ayollar kiyimi', slug: 'ayollar-kiyimi', children: [] },
      { id: 'c-erkaklar', name: 'Erkaklar kiyimi', slug: 'erkaklar-kiyimi', children: [] },
    ],
  },
  {
    id: 'c-uy',
    name: "Uy-ro'zg'or",
    slug: 'uy-rozgor',
    children: [{ id: 'c-idish', name: 'Oshxona idishlari', slug: 'oshxona-idish', children: [] }],
  },
]

type Seed = {
  title: string
  status: 'draft' | 'active' | 'archived'
  category: { id: string; name: string; slug: string }
  image: number | null
  variants: Array<{
    values: Array<[string, string, string]>
    price: number
    stock: number
    reserved: number
  }>
}

const AYOLLAR = { id: 'c-ayollar', name: 'Ayollar kiyimi', slug: 'ayollar-kiyimi' }
const IDISH = { id: 'c-idish', name: 'Oshxona idishlari', slug: 'oshxona-idish' }
const ERKAK = { id: 'c-erkaklar', name: 'Erkaklar kiyimi', slug: 'erkaklar-kiyimi' }
const color = (id: string, value: string): [string, string, string] => [id, value, 'color']
const size = (value: string): [string, string, string] => [`v-${value}`, value, 'size']

const seeds: Seed[] = [
  {
    title: "Atlas ko'ylak, qo'lda tikilgan",
    status: 'active',
    category: AYOLLAR,
    image: 3,
    variants: [
      { values: [color('v-qizil', 'Qizil'), size('S')], price: 45_000_000, stock: 12, reserved: 2 },
      { values: [color('v-qizil', 'Qizil'), size('M')], price: 45_000_000, stock: 8, reserved: 0 },
      { values: [color('v-kok', "Ko'k"), size('S')], price: 47_500_000, stock: 5, reserved: 1 },
      { values: [color('v-kok', "Ko'k"), size('M')], price: 47_500_000, stock: 0, reserved: 0 },
    ],
  },
  {
    title: 'Rishton choynak, 1 litr',
    status: 'active',
    category: IDISH,
    image: 1,
    variants: [{ values: [], price: 18_500_000, stock: 34, reserved: 3 }],
  },
  {
    title: "Adras ro'mol",
    status: 'draft',
    category: AYOLLAR,
    image: null,
    variants: [],
  },
  {
    title: "Piyola to'plami, 6 dona",
    status: 'active',
    category: IDISH,
    image: 4,
    variants: [
      { values: [color('v-oq', 'Oq')], price: 12_000_000, stock: 20, reserved: 0 },
      { values: [color('v-kok', "Ko'k")], price: 12_500_000, stock: 16, reserved: 4 },
    ],
  },
  {
    title: "Erkaklar to'poni, Chust",
    status: 'archived',
    category: ERKAK,
    image: 0,
    variants: [{ values: [], price: 9_500_000, stock: 0, reserved: 0 }],
  },
  {
    title: 'Beqasam chopon',
    status: 'active',
    category: ERKAK,
    image: 5,
    variants: [
      { values: [size('L')], price: 120_000_000, stock: 3, reserved: 1 },
      { values: [size('XL')], price: 120_000_000, stock: 2, reserved: 0 },
    ],
  },
]

const details = seeds.map((seed, i) => {
  const id = `00000000-0000-4000-8000-00000000000${i + 1}`
  const variants = seed.variants.map((v, j) => ({
    id: `${id}-v${j}`,
    sku: [
      'BZ',
      i + 1,
      ...v.values.map(([, value]) => value.toUpperCase().replace(/[^A-Z0-9]/g, '')),
    ].join('-'),
    price_tiyin: v.price,
    stock: v.stock,
    reserved: v.reserved,
    available: v.stock - v.reserved,
    is_active: true,
    attributes: v.values.map(([value_id, value, code]) => ({
      value_id,
      value,
      code,
      name: code === 'color' ? 'Rang' : "O'lcham",
    })),
    created_at: at(10 - i),
    updated_at: at(1),
  }))
  const prices = variants.map((v) => v.price_tiyin)
  const images =
    seed.image === null
      ? []
      : [
          {
            id: `${id}-i0`,
            position: 0,
            status: 'ready',
            original_key: `products/${id}/a.png`,
            thumb_url: img(seed.image),
            medium_url: img(seed.image),
            large_url: img(seed.image),
            created_at: at(3),
          },
          {
            id: `${id}-i1`,
            position: 1,
            status: 'ready',
            original_key: `products/${id}/b.png`,
            thumb_url: img(seed.image + 2),
            medium_url: img(seed.image + 2),
            large_url: img(seed.image + 2),
            created_at: at(3),
          },
        ]
  return {
    id,
    slug: `mahsulot-${i + 1}`,
    title: seed.title,
    status: seed.status,
    category: seed.category,
    min_price_tiyin: prices.length ? Math.min(...prices) : null,
    max_price_tiyin: prices.length ? Math.max(...prices) : null,
    in_stock: variants.some((v) => v.available > 0),
    variants_count: variants.length,
    image_url: seed.image === null ? null : img(seed.image),
    created_at: at(10 - i),
    updated_at: at(1),
    description: "Marg'ilon ustalari tomonidan tabiiy ipakdan tayyorlangan.",
    variants,
    images,
  }
})

const listItems = details.map(({ variants: _v, images: _i, description: _d, ...item }) => item)

const seller = {
  id: 'u-seller',
  phone: '+998901234567',
  full_name: 'Dilnoza Karimova',
  role: 'seller',
  date_joined: at(30),
}

const application = (status: 'approved' | 'pending') => ({
  id: 'app-1',
  shop_name: "Marg'ilon atlas uyi",
  inn: '305123456',
  description: 'Atlas va adras matolari, milliy kiyimlar.',
  status,
  reviewed_at: status === 'approved' ? at(20) : null,
  created_at: at(0),
})

const SHOTS: Shot[] = [
  { name: 'login', path: '/login' },
  { name: 'onboarding-form', path: '/onboarding', role: 'customer', application: 'none' },
  { name: 'onboarding-pending', path: '/onboarding', role: 'customer', application: 'pending' },
  { name: 'dashboard', path: '/', role: 'seller' },
  {
    name: 'products',
    path: '/products',
    role: 'seller',
    prepare: async (page) => {
      await page.getByRole('button', { name: /Variantlar va qoldiq: Atlas/ }).click()
      await page.getByRole('textbox', { name: 'Qoldiq: Qizil / S' }).waitFor()
    },
  },
  { name: 'products-empty', path: '/products', role: 'seller', emptyProducts: true },
  {
    name: 'product-new',
    path: '/products/new',
    role: 'seller',
    prepare: async (page) => {
      await page.getByLabel('Nomi').fill("Adras ko'ylak")
      await page.getByLabel('Kategoriya').selectOption('c-ayollar')
      await page.getByLabel("Xususiyat qo'shish").selectOption('a-rang')
      await page.getByRole('button', { name: "Qo'shish", exact: true }).click()
      await page.getByRole('button', { name: 'Qizil' }).click()
      await page.getByRole('button', { name: "Ko'k" }).click()
      await page.getByLabel("Xususiyat qo'shish").selectOption('a-olcham')
      await page.getByRole('button', { name: "Qo'shish", exact: true }).click()
      await page.getByRole('button', { name: 'M', exact: true }).click()
      await page.getByRole('button', { name: 'L', exact: true }).click()
      await page.getByLabel('Hammasiga narx').fill('385000')
      await page.getByLabel('Hammasiga qoldiq').fill('10')
      await page.getByRole('button', { name: "Qo'llash" }).click()
    },
  },
  { name: 'product-edit', path: `/products/${details[0]!.id}`, role: 'seller' },
]

function parseArgs(argv: string[]) {
  const positional: string[] = []
  let url: string | undefined
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]!
    if (arg === '--url') url = argv[++i]
    else if (arg.startsWith('--url=')) url = arg.slice('--url='.length)
    else positional.push(arg)
  }
  const outDir = positional[0]
  if (!outDir) {
    console.error('Usage: pnpm screenshots:seller <output-dir> [--url <app-url>]')
    process.exit(2)
  }
  return { outDir: resolve(process.cwd(), outDir), url }
}

const json = (route: Route, status: number, body: unknown) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

async function mockApi(page: Page, shot: Shot) {
  await page.route(`${IMAGE_HOST}/**`, (route) => {
    const index = Number(new URL(route.request().url()).pathname.match(/(\d+)\.svg$/)?.[1] ?? 0)
    return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: productSvg(index) })
  })
  await page.route('**/api/**', (route) => {
    const url = new URL(route.request().url())
    const method = route.request().method()
    const path = url.pathname
    if (method === 'POST' && path === '/api/auth/otp/send/') return route.fulfill({ status: 204 })
    if (method === 'POST' && path === '/api/auth/token/refresh/') {
      return json(route, 200, { access: 'fixture-access', refresh: 'fixture-refresh' })
    }
    if (path === '/api/auth/me/')
      return json(route, 200, { ...seller, role: shot.role ?? 'customer' })
    if (path === '/api/auth/seller/application/') {
      const state = shot.application ?? 'approved'
      if (state === 'none') {
        return json(route, 404, {
          error: { code: 'NOT_FOUND', message: 'No application yet.', details: {} },
        })
      }
      return json(route, 200, application(state))
    }
    if (path === '/api/catalog/attributes/') return json(route, 200, attributes)
    if (path === '/api/catalog/categories/') return json(route, 200, categories)
    if (path === '/api/catalog/seller/products/') {
      const status = url.searchParams.get('status')
      const pageSize = Number(url.searchParams.get('page_size') ?? 20)
      let items = shot.emptyProducts ? [] : listItems
      if (status) items = items.filter((item) => item.status === status)
      return json(route, 200, {
        items: items.slice(0, pageSize),
        total: items.length,
        page: 1,
        page_size: pageSize,
      })
    }
    const detail = details.find((d) => path === `/api/catalog/seller/products/${d.id}/`)
    if (detail) return json(route, 200, detail)
    return json(route, 404, { error: { code: 'NOT_FOUND', message: 'Not found', details: {} } })
  })
}

async function checkLayout(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const problems: string[] = []
    const vw = document.documentElement.clientWidth
    if (document.documentElement.scrollWidth > vw) {
      problems.push(
        `horizontal scroll: scrollWidth ${document.documentElement.scrollWidth} > ${vw}`,
      )
    }
    const insideScroller = (el: Element) => {
      for (let p = el.parentElement; p; p = p.parentElement) {
        const o = getComputedStyle(p).overflowX
        if (o === 'auto' || o === 'scroll' || o === 'hidden' || o === 'clip') return true
      }
      return false
    }
    for (const el of Array.from(document.body.querySelectorAll('*'))) {
      const rect = el.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) continue
      if ((rect.right > vw + 1 || rect.left < -1) && !insideScroller(el)) {
        const label = `${el.tagName.toLowerCase()}.${String(el.className).split(' ').slice(0, 3).join('.')}`
        problems.push(
          `outside viewport: ${label} [${Math.round(rect.left)}..${Math.round(rect.right)}]`,
        )
      }
    }
    return problems.slice(0, 10)
  })
}

async function waitForServer(url: string, timeoutMs = 30_000) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 300))
  }
  throw new Error(`Server at ${url} did not start within ${timeoutMs} ms`)
}

function startPreview(): ChildProcess {
  return spawn(`pnpm --filter seller exec vite preview --port ${PREVIEW_PORT} --strictPort`, {
    stdio: 'ignore',
    shell: true,
  })
}

function stopPreview(preview: ChildProcess | undefined) {
  if (!preview?.pid) return
  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(preview.pid), '/T', '/F'], { stdio: 'ignore' })
  } else {
    preview.kill()
  }
}

async function main() {
  const { outDir, url } = parseArgs(process.argv.slice(2))
  await mkdir(outDir, { recursive: true })

  let preview: ChildProcess | undefined
  const baseUrl = url ?? `http://localhost:${PREVIEW_PORT}`
  if (!url) {
    preview = startPreview()
    await waitForServer(baseUrl)
  }

  const browser = await chromium.launch()
  const failures: string[] = []
  try {
    for (const theme of THEMES) {
      for (const width of WIDTHS) {
        const context = await browser.newContext({
          viewport: { width, height: width < 768 ? 800 : 900 },
          deviceScaleFactor: width < 768 ? 2 : 1,
          colorScheme: theme,
          reducedMotion: 'reduce',
          locale: 'uz-UZ',
        })
        await context.addInitScript('globalThis.__name = (fn) => fn')
        await context.addInitScript((mode) => {
          localStorage.setItem('bozorcha.theme', JSON.stringify({ state: { mode }, version: 0 }))
        }, theme)

        for (const shot of SHOTS) {
          const page = await context.newPage()
          const errors: string[] = []
          page.on('console', (msg) => {
            // A 404 for "no application yet" is an expected answer, not a page error.
            if (msg.type() === 'error' && !msg.text().includes('404')) errors.push(msg.text())
          })
          page.on('pageerror', (error) => errors.push(error.message))
          await mockApi(page, shot)
          await page.addInitScript((signedIn) => {
            if (signedIn) localStorage.setItem('bozorcha.refresh', 'fixture-refresh')
            else localStorage.removeItem('bozorcha.refresh')
          }, Boolean(shot.role))
          await page.goto(`${baseUrl}${shot.path}`, { waitUntil: 'networkidle' })
          await shot.prepare?.(page)
          await page.evaluate(() => document.fonts.ready)
          await page.waitForLoadState('networkidle')
          // Interactions may have scrolled; sticky chrome belongs at the top of a full-page shot.
          await page.evaluate(() => window.scrollTo(0, 0))

          const isDark = await page.evaluate(() =>
            document.documentElement.classList.contains('dark'),
          )
          const problems = await checkLayout(page)
          if (isDark !== (theme === 'dark')) problems.push(`theme class mismatch (dark=${isDark})`)
          problems.push(...errors.map((e) => `console: ${e}`))

          const file = resolve(outDir, `${shot.name}-${width}-${theme}.png`)
          await page.screenshot({ path: file, fullPage: true })
          const status = problems.length ? 'FAIL' : 'ok  '
          console.log(`${status} ${shot.name} ${width}px ${theme} -> ${file}`)
          for (const problem of problems) {
            console.log(`       ${problem}`)
            failures.push(`${shot.name} ${width} ${theme}: ${problem}`)
          }
          await page.close()
        }
        await context.close()
      }
    }
  } finally {
    await browser.close()
    stopPreview(preview)
  }

  if (failures.length) {
    console.error(`\n${failures.length} problem(s) found`)
    process.exit(1)
  }
  console.log('\nAll screenshots taken; no layout problems found.')
}

await main()
