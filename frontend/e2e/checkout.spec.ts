/**
 * Shop scenarios: a guest buys a product end to end, and two customers race for the last
 * unit of a product.
 */
import { expect, test, type Page } from '@playwright/test'
import {
  api,
  closeContexts,
  inSearch,
  createProduct,
  freshPhone,
  issueTokens,
  json,
  SELLERS,
  shot,
  signedInContext,
  SHOP,
  waitFor,
} from './helpers'

test.afterEach(closeContexts)

/** The checkout form; the phone may already be filled in from the profile. */
async function fillCheckout(page: Page, name: string): Promise<void> {
  await page.getByLabel('Qabul qiluvchi').fill(name)
  await page.getByLabel('Telefon raqam').fill('90 123 45 67')
  await page.getByLabel('Viloyat').selectOption({ index: 1 })
  await page.getByLabel('Shahar yoki tuman').fill('Toshkent')
  await page.getByLabel("Ko'cha, uy, xonadon").fill("Amir Temur ko'chasi, 1-uy")
}

/** On the order page of a RESERVED order: pay with the test method, land on PAID. */
async function payWithTestMethod(page: Page): Promise<void> {
  await page.getByRole('radio', { name: /Test to'lov/ }).check()
  await page.getByRole('button', { name: "Test to'lovini o'tkazish" }).click()
  await expect(page.getByText("To'lov qabul qilindi")).toBeVisible()
}

test('guest: search, cart, login, checkout, test payment, order in the list', async ({ page }) => {
  const [seller] = issueTokens([SELLERS.texnomart.phone])
  const title = `E2E choynak ${Date.now()}`
  await createProduct(seller!, { title, stock: 5, price: 185_000_00 })
  const anonymous = await api()
  await waitFor(async () => {
    return inSearch(anonymous, title)
  }, 'the new product in search')

  // Guest: search and add to the cart.
  await page.goto(SHOP)
  const search = page.getByRole('combobox', { name: /qidirish/i })
  await search.fill(title)
  await search.press('Enter')
  await page.getByRole('link', { name: title }).first().click()
  await page.getByRole('button', { name: 'Savatchaga' }).click()
  await expect(page.getByText("Savatchaga qo'shildi")).toBeVisible()
  await page.goto(`${SHOP}/cart`)
  await shot(page, '1-guest-cart')
  await page.getByRole('button', { name: 'Rasmiylashtirish' }).click()

  // Login with the dev OTP code; the guest cart is merged into the customer's.
  const phone = freshPhone()
  await page.getByLabel('Telefon raqam').fill(phone.slice(4))
  await page.getByRole('button', { name: 'Kod olish' }).click()
  await page.getByRole('heading', { name: 'SMS kodni kiriting' }).waitFor()
  await page.getByRole('textbox').first().click()
  await page.keyboard.type('000000')

  // Checkout.
  await expect(page.getByRole('heading', { name: 'Rasmiylashtirish' })).toBeVisible()
  await expect(page.getByText(title)).toBeVisible()
  await fillCheckout(page, 'E2E Xaridor')
  const submit = page.getByRole('button', { name: 'Buyurtma berish' })
  await expect(submit).toBeEnabled()
  await submit.click()
  await expect(page.getByRole('timer')).toBeVisible()
  await shot(page, '1-order-reserved')
  const orderId = page.url().split('/orders/')[1]!.split(/[/?]/)[0]!

  await payWithTestMethod(page)
  await shot(page, '1-payment-paid')

  await page.goto(`${SHOP}/orders`)
  const number = `#${orderId.slice(0, 8).toUpperCase()}`
  const row = page.getByRole('link', { name: new RegExp(number) })
  await expect(row).toBeVisible()
  await expect(page.getByText("To'landi").first()).toBeVisible()
  await shot(page, '1-my-orders')
})

test('two customers race for the last unit: one PAID, the other CANCELLED', async ({ browser }) => {
  const [seller, first, second] = issueTokens([SELLERS.texnomart.phone, freshPhone(), freshPhone()])
  const { variantId } = await createProduct(seller!, {
    title: `E2E oxirgi dona ${Date.now()}`,
    stock: 1,
    price: 99_000_00,
  })

  const pages: Page[] = []
  for (const customer of [first!, second!]) {
    const client = await api(customer)
    await client.delete('/api/cart/')
    await json(await client.post('/api/cart/items/', { data: { variant_id: variantId, qty: 1 } }))
    await client.dispose()
    const page = await (await signedInContext(browser, customer)).newPage()
    await page.goto(`${SHOP}/checkout`)
    await fillCheckout(page, 'E2E Poyga')
    pages.push(page)
  }

  // Both submit at the same moment; the catalog reserves the single unit for one of them.
  // The button stays disabled until the cart has loaded: wait for it, or a click is lost.
  const submits = pages.map((page) => page.getByRole('button', { name: 'Buyurtma berish' }))
  for (const submit of submits) await expect(submit).toBeEnabled()
  await Promise.all(submits.map((submit) => submit.click()))
  const outcomes = await Promise.all(
    pages.map(async (page) => {
      const reserved = page.getByRole('timer')
      const cancelled = page.getByText('Buyurtma bekor qilindi')
      await expect(reserved.or(cancelled)).toBeVisible()
      return (await reserved.isVisible()) ? 'RESERVED' : 'CANCELLED'
    }),
  )
  expect([...outcomes].sort()).toEqual(['CANCELLED', 'RESERVED'])

  const winner = pages[outcomes.indexOf('RESERVED')]!
  const loser = pages[outcomes.indexOf('CANCELLED')]!
  await expect(
    loser.getByTestId('status-panel').getByText('Mahsulot omborda qolmagan edi.'),
  ).toBeVisible()
  await shot(loser, '4-race-cancelled')
  await payWithTestMethod(winner)
  await shot(winner, '4-race-paid')
})
