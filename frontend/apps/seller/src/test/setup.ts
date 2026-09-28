import '@testing-library/jest-dom/vitest'
import '../i18n'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// jsdom has no scrolling; the router's ScrollRestoration calls it on every navigation.
window.scrollTo = vi.fn() as unknown as typeof window.scrollTo

afterEach(() => {
  cleanup()
  localStorage.clear()
})
