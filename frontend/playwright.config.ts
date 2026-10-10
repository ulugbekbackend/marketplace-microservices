/**
 * End-to-end tests against the running stack (`make up && make seed`), not a mocked API.
 *
 *   pnpm test:e2e                 (or `make test-e2e` from the repository root)
 *
 * Needs DEBUG=True on the stack: test users get their tokens from `manage.py issue_tokens`,
 * and payments go through the payment service's mock provider.
 */
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  // One stack, shared stock and orders: scenarios run one after another.
  workers: 1,
  fullyParallel: false,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  retries: 0,
  reporter: [['list']],
  use: {
    viewport: { width: 1280, height: 900 },
    // Chromium resolves *.localhost to ::1 too; Docker Desktop's IPv6 port forward resets
    // connections under load, so the browser goes to the gateway over IPv4 like the API does.
    launchOptions: { args: ['--host-resolver-rules=MAP *.localhost 127.0.0.1'] },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
})
