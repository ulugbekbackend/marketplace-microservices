import '@testing-library/jest-dom/vitest'
import '../i18n'
import { cleanup, configure } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// jsdom has no scrolling; the router's ScrollRestoration calls it on every navigation.
window.scrollTo = vi.fn() as unknown as typeof window.scrollTo

// Lazy routes load on first visit; under a parallel `pnpm -r test` that can exceed the 1 s default.
configure({ asyncUtilTimeout: 5000 })

afterEach(() => {
  cleanup()
  localStorage.clear()
})
