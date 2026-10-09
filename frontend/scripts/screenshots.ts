/**
 * Screenshots of the shop app with a mocked API (Playwright route interception).
 *
 *   pnpm build
 *   pnpm screenshots <output-dir> [--url http://localhost:4179]
 *
 * Without --url the script serves the built app with `vite preview` itself. Every page is shot at
 * 360px and 1280px in light and dark mode. The run fails if a page scrolls horizontally, an
 * element sticks out of the viewport, or the page logs errors.
 */
import { spawn, type ChildProcess } from 'node:child_process'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium, type Page, type Route } from '@playwright/test'
import {
  cart,
  categories,
  cleanCart,
  customer,
  IMAGE_HOST,
  ORDER_ID,
  orderList,
  productDetail,
  productSvg,
  reservedOrder,
  searchFacets,
  searchItems,
  shop,
} from './fixtures'

const PREVIEW_PORT = 4179
const WIDTHS = [360, 1280] as const
const THEMES = ['light', 'dark'] as const

type Shot = {
  name: string
  path: string
  /** Start with a stored session (the mocked refresh endpoint signs the customer in). */
  signedIn?: boolean
  prepare?: (page: Page) => Promise<void>
  /** Console errors the shot causes on purpose (e.g. the browser logging a mocked 503). */
  expectedConsole?: RegExp
}

const SHOTS: Shot[] = [
  { name: 'home', path: '/' },
  { name: 'catalog', path: '/catalog/kiyim' },
  {
    name: 'search',
    path: "/catalog?q=ko'ylak&attr%5Bcolor%5D=qizil&price_min=10000000&price_max=49999999",
  },
  {
    name: 'catalog-filters',
    path: '/catalog/kiyim?attr%5Bcolor%5D=qizil&attr%5Bsize%5D=M',
    // The filters live in a drawer below 1024px.
    prepare: async (page) => {
      const button = page.getByRole('button', { name: /^Filtrlar( \(\d+\))?$/ })
      if (await button.isVisible()) {
        await button.click()
        await page.getByRole('dialog', { name: 'Filtrlar' }).waitFor()
      }
    },
  },
  { name: 'search-empty', path: '/catalog?q=velosiped' },
  {
    name: 'search-unavailable',
    path: '/catalog?q=down',
    expectedConsole: /status of 503/,
    // 5xx answers are retried with backoff before the error state shows.
    prepare: async (page) => {
      await page.getByRole('alert').waitFor({ timeout: 15_000 })
    },
  },
  {
    name: 'autocomplete',
    path: '/',
    prepare: async (page) => {
      const input = page.locator('input[role="combobox"]:visible')
      await input.click()
      await input.pressSequentially('atl')
      await page.locator('[role="listbox"]:visible').waitFor()
      await page.keyboard.press('ArrowDown')
      await page.keyboard.press('ArrowDown')
    },
  },
  { name: 'product', path: '/p/atlas-koylak' },
  { name: 'shop', path: '/shop/margilon-atlas' },
  { name: 'cart', path: '/cart' },
  { name: 'cart-empty', path: '/cart?empty' },
  { name: 'checkout', path: '/checkout?clean', signedIn: true },
  { name: 'order-reserved', path: `/orders/${ORDER_ID}`, signedIn: true },
  {
    name: 'payment-waiting',
    path: `/orders/${ORDER_ID}/payment?provider=payme`,
    signedIn: true,
  },
  { name: 'orders', path: '/orders', signedIn: true },
  {
    name: 'login-otp',
    path: '/login',
    prepare: async (page) => {
      await page.getByLabel('Telefon raqam').fill('901234567')
      await page.getByRole('button', { name: 'Kod olish' }).click()
      await page.getByRole('heading', { name: 'SMS kodni kiriting' }).waitFor()
      await page.keyboard.type('48')
    },
  },
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
    console.error('Usage: pnpm screenshots <output-dir> [--url <app-url>]')
    process.exit(2)
  }
  return { outDir: resolve(process.cwd(), outDir), url }
}

const json = (route: Route, status: number, body: unknown) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

/** Answers every API call from fixtures; unknown endpoints return the shared 404 shape. */
async function mockApi(page: Page) {
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
    if (path === '/api/auth/me/') return json(route, 200, customer)
    if (path === '/api/orders/') {
      return json(route, 200, { items: orderList, total: orderList.length, page: 1, page_size: 10 })
    }
    if (path === `/api/orders/${ORDER_ID}/`) return json(route, 200, reservedOrder())
    if (path === `/api/orders/${ORDER_ID}/status/`) {
      const { status, reserved_until } = reservedOrder()
      return json(route, 200, { status, reserved_until })
    }
    if (path === '/api/catalog/categories/') return json(route, 200, categories)
    if (path === '/api/search/suggest') {
      const q = (url.searchParams.get('q') ?? '').toLowerCase()
      const items = q.length < 2 ? [] : searchItems.filter((p) => p.title.toLowerCase().includes(q))
      return json(route, 200, {
        items: items.slice(0, 8).map(({ id, slug, title }) => ({ id, slug, title })),
      })
    }
    if (path === '/api/search') {
      const q = (url.searchParams.get('q') ?? '').toLowerCase()
      if (q === 'down') {
        return json(route, 503, {
          error: { code: 'SEARCH_UNAVAILABLE', message: 'Search is unavailable', details: null },
        })
      }
      const page = Number(url.searchParams.get('page') ?? 1)
      const pageSize = Number(url.searchParams.get('page_size') ?? 24)
      const seller = url.searchParams.get('seller')
      let items = searchItems.filter(
        (p) => (!seller || p.seller_id === seller) && (!q || p.title.toLowerCase().includes(q)),
      )
      if (url.searchParams.get('in_stock') === 'true') items = items.filter((p) => p.in_stock)
      const sort = url.searchParams.get('sort')
      if (sort === 'price_asc') items = [...items].sort((a, b) => a.min_price - b.min_price)
      if (sort === 'price_desc') items = [...items].sort((a, b) => b.min_price - a.min_price)
      // Pretend there is a longer catalog so pagination is visible.
      const total = q ? items.length : seller ? 48 : 186
      return json(route, 200, {
        items: items.slice(0, pageSize),
        total,
        page,
        page_size: pageSize,
        facets: searchFacets(url.searchParams.getAll('attr[color]')),
      })
    }
    if (method === 'GET' && path === '/api/cart/') {
      // "?empty" on the page URL shows the empty cart.
      const search = new URL(page.url()).search
      if (search === '?clean') return json(route, 200, cleanCart)
      const empty = search === '?empty'
      return json(
        route,
        200,
        empty
          ? {
              ...cart,
              groups: [],
              total_tiyin: 0,
              items_count: 0,
              has_unavailable: false,
              has_price_changes: false,
              removed: [],
            }
          : cart,
      )
    }
    if (path === `/api/catalog/products/${productDetail.slug}/`)
      return json(route, 200, productDetail)
    if (path === `/api/catalog/shops/${shop.slug}/`) return json(route, 200, shop)
    return json(route, 404, { error: { code: 'NOT_FOUND', message: 'Not found', details: null } })
  })
}

/** Layout checks: page-level horizontal scroll and elements poking out of the viewport. */
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
  // One constant command string: Windows needs a shell to run pnpm.cmd.
  return spawn(`pnpm --filter shop exec vite preview --port ${PREVIEW_PORT} --strictPort`, {
    stdio: 'ignore',
    shell: true,
  })
}

/** On Windows the preview runs under a shell: kill the whole process tree. */
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
        // tsx keeps function names via a __name helper that page.evaluate code also references.
        await context.addInitScript('globalThis.__name = (fn) => fn')
        await context.addInitScript((mode) => {
          localStorage.setItem('bozorcha.theme', JSON.stringify({ state: { mode }, version: 0 }))
        }, theme)

        for (const shot of SHOTS) {
          const page = await context.newPage()
          const errors: string[] = []
          page.on('console', (msg) => msg.type() === 'error' && errors.push(msg.text()))
          page.on('pageerror', (error) => errors.push(error.message))
          await mockApi(page)
          // Storage is shared by the context: every shot sets the session it needs.
          await page.addInitScript((signedIn) => {
            if (signedIn) localStorage.setItem('bozorcha.refresh', 'fixture-refresh')
            else localStorage.removeItem('bozorcha.refresh')
          }, Boolean(shot.signedIn))
          await page.goto(`${baseUrl}${shot.path}`, { waitUntil: 'networkidle' })
          await shot.prepare?.(page)
          await page.evaluate(() => document.fonts.ready)
          await page.waitForLoadState('networkidle')

          const isDark = await page.evaluate(() =>
            document.documentElement.classList.contains('dark'),
          )
          const problems = await checkLayout(page)
          if (isDark !== (theme === 'dark')) problems.push(`theme class mismatch (dark=${isDark})`)
          problems.push(
            ...errors.filter((e) => !shot.expectedConsole?.test(e)).map((e) => `console: ${e}`),
          )

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
