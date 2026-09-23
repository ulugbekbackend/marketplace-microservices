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
import { categories, IMAGE_HOST, productDetail, products, productSvg, shop } from './fixtures'

const PREVIEW_PORT = 4179
const WIDTHS = [360, 1280] as const
const THEMES = ['light', 'dark'] as const

type Shot = { name: string; path: string; prepare?: (page: Page) => Promise<void> }

const SHOTS: Shot[] = [
  { name: 'home', path: '/' },
  { name: 'catalog', path: '/catalog/kiyim' },
  { name: 'product', path: '/p/atlas-koylak' },
  { name: 'shop', path: '/shop/margilon-atlas' },
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
    if (path === '/api/catalog/categories/') return json(route, 200, categories)
    if (path === '/api/catalog/products/') {
      const page = Number(url.searchParams.get('page') ?? 1)
      const pageSize = Number(url.searchParams.get('page_size') ?? 24)
      const seller = url.searchParams.get('seller')
      const items = seller ? products.filter((p) => p.seller.slug === seller) : products
      // Pretend there is a longer catalog so pagination is visible.
      return json(route, 200, {
        items: items.slice(0, pageSize),
        total: seller ? 48 : 186,
        page,
        page_size: pageSize,
      })
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
          await page.goto(`${baseUrl}${shot.path}`, { waitUntil: 'networkidle' })
          await shot.prepare?.(page)
          await page.evaluate(() => document.fonts.ready)
          await page.waitForLoadState('networkidle')

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
