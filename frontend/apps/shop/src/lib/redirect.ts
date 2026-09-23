/** Only same-site relative paths are allowed as a post-login redirect. */
export function safeNext(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.startsWith('/login')) {
    return '/'
  }
  return value
}
