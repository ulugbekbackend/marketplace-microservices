/** Only same-site relative paths are allowed as a post-login redirect. */
export function safeNext(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.startsWith('/login')) {
    return '/'
  }
  return value
}

/** Leaves the app for a full page URL (a payment provider's checkout). */
export function leaveTo(url: string): void {
  window.location.assign(url)
}
