// Overselling test: 100 customers buy the same variant, which has 10 units, at the same time.
// Each one adds it to the cart, checks out, waits for the reservation and pays (mock).
// Exactly 10 orders may end PAID; tests/load/verify.py checks the rest afterwards.
//
//   make load-test          (prepare -> this script in the grafana/k6 container -> verify -> plot)
import http from 'k6/http'
import { check, sleep } from 'k6'
import { Counter, Trend } from 'k6/metrics'

const setup = JSON.parse(open('./results/setup.json'))
const BASE = __ENV.GATEWAY || 'http://traefik'
const POLL_SECONDS = 0.5
const SETTLE_SECONDS = 60

const ADDRESS = {
  full_name: 'Load Test',
  phone: '+998901234567',
  region: 'Toshkent shahri',
  city: 'Toshkent',
  street: 'Amir Temur 1',
}

const outcomes = new Counter('order_outcomes')
const serverErrors = new Counter('server_errors')
const settleTime = new Trend('order_settle_ms', true)

export const options = {
  scenarios: {
    buyers: {
      executor: 'per-vu-iterations',
      vus: setup.customers.length,
      iterations: 1,
      maxDuration: '3m',
    },
  },
  // The pass/fail rules (10 PAID, stock 0, no 5xx...) are checked by verify.py afterwards.
}

function headers(token, extra = {}) {
  return {
    headers: {
      Host: 'api.localhost',
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...extra,
    },
  }
}

function request(method, path, token, body = null, extra = {}) {
  const response = http.request(method, `${BASE}${path}`, body && JSON.stringify(body), {
    ...headers(token, extra),
    tags: { name: `${method} ${path.replace(/[0-9a-f-]{36}/g, ':id')}` },
  })
  if (response.status >= 500) serverErrors.add(1)
  return response
}

function waitWhile(token, orderId, statuses) {
  const deadline = Date.now() + SETTLE_SECONDS * 1000
  while (Date.now() < deadline) {
    const response = request('GET', `/api/orders/${orderId}/status/`, token)
    const status = response.status === 200 ? response.json('status') : null
    if (status && !statuses.includes(status)) return status
    sleep(POLL_SECONDS)
  }
  return 'TIMEOUT'
}

export default function () {
  const token = setup.customers[__VU - 1]
  const start = Date.now()

  const added = request('POST', '/api/cart/items/', token, {
    variant_id: setup.variant_id,
    qty: 1,
  })
  check(added, { 'added to cart': (r) => r.status === 200 })

  const placed = request(
    'POST',
    '/api/orders/checkout/',
    token,
    { address: ADDRESS },
    {
      'Idempotency-Key': `load-${__VU}-${start}`,
    },
  )
  // Checkout may already refuse with 409 when the catalog shows no stock left.
  if (placed.status === 409) {
    outcomes.add(1, { outcome: 'REFUSED' })
    return
  }
  if (!check(placed, { 'checkout accepted': (r) => r.status === 202 })) {
    outcomes.add(1, { outcome: `CHECKOUT_${placed.status}` })
    return
  }
  const orderId = placed.json('order_id')

  let status = waitWhile(token, orderId, ['PENDING'])
  if (status === 'RESERVED') {
    const paid = request('POST', `/api/payments/mock/${orderId}/pay`, token)
    check(paid, { 'payment accepted': (r) => r.status === 200 })
    status = waitWhile(token, orderId, ['RESERVED'])
  }
  settleTime.add(Date.now() - start)
  outcomes.add(1, { outcome: status })
}

export function handleSummary(data) {
  return { 'results/summary.json': JSON.stringify(data, null, 2) }
}
