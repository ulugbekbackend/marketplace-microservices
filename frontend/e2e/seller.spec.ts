/**
 * Seller scenarios: a new product with variants and an image reaches search within ten
 * seconds, and shipping a sub-order shows up on the customer's order page.
 */
import { deflateSync, crc32 } from 'node:zlib'
import { expect, test } from '@playwright/test'
import {
  api,
  inSearch,
  createProduct,
  freshPhone,
  issueTokens,
  json,
  paidOrder,
  SELLER,
  SELLERS,
  shot,
  signedInContext,
  SHOP,
  waitFor,
} from './helpers'

/** A solid colour PNG, built in memory so the repository holds no binary fixture. */
function png(width: number, height: number, [r, g, b]: [number, number, number]): Buffer {
  const chunk = (type: string, data: Buffer) => {
    const head = Buffer.alloc(8)
    head.writeUInt32BE(data.length, 0)
    head.write(type, 4, 'ascii')
    const crc = Buffer.alloc(4)
    crc.writeUInt32BE(crc32(Buffer.concat([head.subarray(4), data])), 0)
    return Buffer.concat([head, data, crc])
  }
  const header = Buffer.alloc(13)
  header.writeUInt32BE(width, 0)
  header.writeUInt32BE(height, 4)
  header.set([8, 2, 0, 0, 0], 8) // 8 bit, truecolour
  const row = Buffer.concat([Buffer.from([0]), Buffer.alloc(width * 3)])
  for (let x = 0; x < width; x++) row.set([r, g, b], 1 + x * 3)
  const pixels = Buffer.concat(Array.from({ length: height }, () => row))
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header),
    chunk('IDAT', deflateSync(pixels)),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

test('seller: a new product with variants and an image is searchable within 10 s', async ({
  browser,
}) => {
  const [seller] = issueTokens([SELLERS.texnomart.phone])
  const page = await (await signedInContext(browser, seller!)).newPage()
  // The cabinet builds SKUs from the title's words, so the unique part must be a word.
  const token = Array.from(
    { length: 6 },
    () => 'abcdefghijkmnpqrstuvwxyz'[Math.floor(Math.random() * 24)],
  ).join('')
  const title = `E2E ${token} atlas ko'ylak`

  await page.goto(`${SELLER}/products/new`)
  await page.getByLabel('Nomi').fill(title)
  await page.getByLabel('Kategoriya').selectOption({ index: 1 })
  await page.getByLabel("Xususiyat qo'shish").selectOption({ label: 'Rang' })
  await page.getByRole('button', { name: "Qo'shish", exact: true }).click()
  await page.getByRole('button', { name: 'qizil', exact: true }).click()
  await page.getByRole('button', { name: "ko'k", exact: true }).click()
  await page.getByLabel('Hammasiga narx').fill('385000')
  await page.getByLabel('Hammasiga qoldiq').fill('6')
  await page.getByRole('button', { name: "Qo'llash" }).click()
  await page.getByLabel('Mahsulot holati').selectOption('active')
  await page.getByRole('button', { name: 'Saqlash' }).first().click()
  await expect(page.getByText('Mahsulot saqlandi', { exact: true })).toBeVisible()
  // The product is on sale from this moment: search must find it within 10 s, while the
  // seller goes on to upload the image.
  const savedAt = Date.now()
  const anonymous = await api()
  const searchable = waitFor(
    async () => {
      return (await inSearch(anonymous, title)) ? Date.now() : null
    },
    'the product in search',
    10_000,
  )

  await page.locator('input[type="file"]').setInputFiles({
    name: 'atlas.png',
    mimeType: 'image/png',
    buffer: png(320, 320, [15, 110, 86]),
  })
  await expect(page.getByText('Tayyor').first()).toBeVisible({ timeout: 30_000 })
  await shot(page, '2-seller-product')

  const foundAt = await searchable
  console.log(`searchable after ${foundAt - savedAt} ms`)
  expect(foundAt - savedAt).toBeLessThan(10_000)

  const shop = await (await browser.newContext()).newPage()
  await shop.goto(`${SHOP}/catalog?q=${encodeURIComponent(title)}`)
  await expect(shop.getByRole('link', { name: title }).first()).toBeVisible()
  await shot(shop, '2-shop-search')
})

test('seller ships a sub-order and the customer sees it on the order page', async ({ browser }) => {
  const [seller, customer] = issueTokens([SELLERS.chilonzor.phone, freshPhone()])
  const { variantId } = await createProduct(seller!, {
    title: `E2E quloqchin ${Date.now()}`,
    stock: 3,
    price: 249_000_00,
  })
  const orderId = await paidOrder(customer!, variantId)

  const sellerApi = await api(seller)
  const subOrder = await waitFor(async () => {
    const page = await json<{ items: { id: string; order_id: string }[] }>(
      await sellerApi.get('/api/orders/seller/', { params: { page_size: 50 } }),
    )
    return page.items.find((item) => item.order_id === orderId)
  }, 'the sub-order in the seller cabinet')

  const customerPage = await (await signedInContext(browser, customer!)).newPage()
  await customerPage.goto(`${SHOP}/orders/${orderId}`)
  await expect(customerPage.getByText("To'lov qabul qilindi")).toBeVisible()

  const sellerPage = await (await signedInContext(browser, seller!)).newPage()
  await sellerPage.goto(`${SELLER}/orders/${subOrder.id}`)
  await sellerPage.getByRole('button', { name: 'Qabul qilish' }).click()
  await expect(sellerPage.getByText('Buyurtma qabul qilindi')).toBeVisible()
  await sellerPage.getByRole('button', { name: "Jo'natish" }).click()
  await sellerPage.getByLabel('Trek raqami').fill('UZP123456789')
  await sellerPage.getByRole('button', { name: "Jo'natildi" }).click()
  await expect(sellerPage.getByText("Buyurtma jo'natildi")).toBeVisible()
  await shot(sellerPage, '3-seller-shipped')

  // The customer comes back to the page (statuses after payment are not polled).
  await customerPage.reload()
  const shopGroup = customerPage.getByRole('region', { name: SELLERS.chilonzor.shop })
  await expect(shopGroup.getByText("Yo'lda").first()).toBeVisible()
  await expect(shopGroup.getByTestId('tracking')).toContainText('UZP123456789')
  await shot(customerPage, '3-customer-shipped')
})
