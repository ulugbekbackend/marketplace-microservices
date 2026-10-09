/**
 * What the scenarios share: test users with real tokens, a signed-in browser context per
 * app, an API client on the gateway and screenshots for the README.
 */
import { execFileSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  expect,
  request,
  type APIRequestContext,
  type Browser,
  type BrowserContext,
  type Page,
} from '@playwright/test'

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')
export const SHOP = 'http://shop.localhost'
export const SELLER = 'http://seller.localhost'
const GATEWAY = process.env.GATEWAY_URL ?? 'http://127.0.0.1'
const SHOTS = resolve(ROOT, 'docs', 'screenshots', 'e2e')

/** Demo sellers from `make seed` (py_common.demo.SELLERS). */
export const SELLERS = {
  texnomart: { phone: '+998901110001', shop: 'Texnomart Plus' },
  chilonzor: { phone: '+998901110003', shop: 'Chilonzor Elektronika' },
} as const

export type TestUser = {
  phone: string
  user_id: string
  role: 'customer' | 'seller' | 'admin'
  access: string
  refresh: string
}

/** Token pairs straight from the auth service (DEBUG only), no OTP round trip. */
export function issueTokens(phones: string[]): TestUser[] {
  const args = phones.flatMap((phone) => ['--phone', phone])
  const out = execFileSync(
    'docker',
    [
      'compose', '-f', 'infra/docker-compose.yml', '--env-file', '.env',
      'exec', '-T', 'auth', 'python', 'manage.py', 'issue_tokens', ...args,
    ],
    { cwd: ROOT, encoding: 'utf8' },
  ) // prettier-ignore
  return JSON.parse(out.trim().split('\n').at(-1)!) as TestUser[]
}

/** A random customer phone that has never logged in. */
export function freshPhone(): string {
  return `+99890${String(Math.floor(1_000_000 + Math.random() * 8_999_999))}`
}

/** A browser context that starts signed in as `user` (the app refreshes the stored token). */
export async function signedInContext(browser: Browser, user: TestUser): Promise<BrowserContext> {
  const context = await browser.newContext()
  // Only the first load: later loads must keep the token the app rotated.
  await context.addInitScript((token) => {
    if (!localStorage.getItem('bozorcha.refresh')) localStorage.setItem('bozorcha.refresh', token)
  }, user.refresh)
  return context
}

/** The gateway as one user (or anonymous): JSON in, JSON out. */
export async function api(user?: TestUser): Promise<APIRequestContext> {
  return request.newContext({
    baseURL: GATEWAY,
    extraHTTPHeaders: {
      Host: 'api.localhost',
      ...(user ? { Authorization: `Bearer ${user.access}` } : {}),
    },
  })
}

export async function json<T>(response: Awaited<ReturnType<APIRequestContext['get']>>): Promise<T> {
  expect(response.ok(), `${response.url()} -> ${response.status()} ${await response.text()}`).toBe(
    true,
  )
  return (await response.json()) as T
}

/** Polls `probe` until it returns something truthy. */
export async function waitFor<T>(
  probe: () => Promise<T | null | undefined | false>,
  what: string,
  timeoutMs = 20_000,
): Promise<T> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const value = await probe()
    if (value) return value
    await new Promise((r) => setTimeout(r, 300))
  }
  throw new Error(`timed out waiting for ${what}`)
}

export async function shot(page: Page, name: string): Promise<void> {
  mkdirSync(SHOTS, { recursive: true })
  await page.screenshot({ path: resolve(SHOTS, `${name}.png`), fullPage: true })
}

/* ------------------------------------------------------------------ API set-ups */

type OrderStatus = { status: string }
type Category = { id: string; children: Category[] }

export async function orderStatus(client: APIRequestContext, orderId: string): Promise<string> {
  return (await json<OrderStatus>(await client.get(`/api/orders/${orderId}/status/`))).status
}

/** The first leaf category of the catalog tree. */
export async function leafCategory(client: APIRequestContext): Promise<string> {
  let node = (await json<Category[]>(await client.get('/api/catalog/categories/')))[0]!
  while (node.children.length) node = node.children[0]!
  return node.id
}

/** A product on sale with one plain variant; returns its slug and variant id. */
export async function createProduct(
  seller: TestUser,
  { title, stock, price }: { title: string; stock: number; price: number },
): Promise<{ slug: string; variantId: string }> {
  const client = await api(seller)
  const product = await json<{ id: string; slug: string }>(
    await client.post('/api/catalog/seller/products/', {
      data: { title, description: '', category_id: await leafCategory(client), status: 'draft' },
    }),
  )
  const sku = `E2E-${Date.now()}`
  const variant = await json<{ id: string }>(
    await client.post(`/api/catalog/seller/products/${product.id}/variants/`, {
      data: { sku, price_tiyin: price, stock, attribute_value_ids: [] },
    }),
  )
  await json(
    await client.patch(`/api/catalog/seller/products/${product.id}/`, {
      data: { status: 'active' },
    }),
  )
  await client.dispose()
  return { slug: product.slug, variantId: variant.id }
}

/** Cart -> checkout -> RESERVED -> mock payment -> PAID, all through the API. */
export async function paidOrder(customer: TestUser, variantId: string): Promise<string> {
  const client = await api(customer)
  await client.delete('/api/cart/')
  await json(await client.post('/api/cart/items/', { data: { variant_id: variantId, qty: 1 } }))
  const { order_id: orderId } = await json<{ order_id: string }>(
    await client.post('/api/orders/checkout/', {
      data: {
        address: {
          full_name: 'E2E Xaridor',
          phone: '+998901234567',
          region: 'Toshkent shahri',
          city: 'Toshkent',
          street: 'Amir Temur 1',
        },
      },
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    }),
  )
  await waitFor(async () => (await orderStatus(client, orderId)) === 'RESERVED', 'RESERVED')
  await json(await client.post(`/api/payments/mock/${orderId}/pay`))
  await waitFor(async () => (await orderStatus(client, orderId)) === 'PAID', 'PAID')
  await client.dispose()
  return orderId
}

/** True once search returns a product with exactly this title (search is fuzzy). */
export async function inSearch(client: APIRequestContext, title: string): Promise<boolean> {
  const found = await json<{ items: { title: string }[] }>(
    await client.get('/api/search', { params: { q: title, sort: 'newest' } }),
  )
  return found.items.some((item) => item.title === title)
}
