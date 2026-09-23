export const REFRESH_TOKEN_KEY = 'bozorcha.refresh'

export type TokenStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

export type TokenSnapshot = {
  /** A refresh token exists, so the user is (or can silently become) signed in. */
  hasSession: boolean
}

/**
 * Access token lives only in memory; the refresh token is persisted so a reload can restore the
 * session. Subscribers are notified on every change (useSyncExternalStore-compatible).
 */
export class TokenStore {
  private access: string | null = null
  private snapshot: TokenSnapshot
  private readonly listeners = new Set<() => void>()
  private readonly storage: TokenStorage | null

  constructor(storage: TokenStorage | null = safeLocalStorage()) {
    this.storage = storage
    this.snapshot = { hasSession: this.getRefresh() !== null }
  }

  getAccess(): string | null {
    return this.access
  }

  getRefresh(): string | null {
    try {
      return this.storage?.getItem(REFRESH_TOKEN_KEY) ?? null
    } catch {
      return null
    }
  }

  set(tokens: { access: string; refresh: string }): void {
    this.access = tokens.access
    try {
      this.storage?.setItem(REFRESH_TOKEN_KEY, tokens.refresh)
    } catch {
      // storage full or blocked: the session lasts until reload
    }
    this.emit()
  }

  clear(): void {
    this.access = null
    try {
      this.storage?.removeItem(REFRESH_TOKEN_KEY)
    } catch {
      // ignore
    }
    this.emit()
  }

  getSnapshot = (): TokenSnapshot => this.snapshot

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private emit(): void {
    const hasSession = this.getRefresh() !== null || this.access !== null
    if (hasSession !== this.snapshot.hasSession) this.snapshot = { hasSession }
    this.listeners.forEach((listener) => listener())
  }
}

function safeLocalStorage(): TokenStorage | null {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null
  } catch {
    return null
  }
}
