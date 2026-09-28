import '@testing-library/jest-dom/vitest'
import '../i18n'
import { cleanup, configure } from '@testing-library/react'
import { afterEach } from 'vitest'

// Lazy routes load on first visit; under a parallel `pnpm -r test` that can exceed the 1 s default.
configure({ asyncUtilTimeout: 5000 })

afterEach(() => {
  cleanup()
  localStorage.clear()
})
