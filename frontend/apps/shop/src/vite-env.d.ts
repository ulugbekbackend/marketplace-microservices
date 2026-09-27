/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  /** "true" shows the dev-only mock payment button in production builds. */
  readonly VITE_MOCK_PAYMENT?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
