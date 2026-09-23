/** Error codes produced by the client itself (not by a service). */
export const CLIENT_ERROR = {
  NETWORK: 'NETWORK_ERROR',
  ABORTED: 'ABORTED',
  INVALID_RESPONSE: 'INVALID_RESPONSE',
} as const

/** Typed form of the shared `{"error": {"code", "message", "details"}}` response. */
export class ApiError extends Error {
  override readonly name = 'ApiError'
  readonly status: number
  readonly code: string
  readonly details: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }

  /** True for 4xx responses: retrying the same request will not help. */
  get isClientError(): boolean {
    return this.status >= 400 && this.status < 500
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

/**
 * Builds an ApiError from a parsed response body. Understands the shared error shape and falls
 * back to DRF-style `{"detail": "..."}` or a generic HTTP error.
 */
export function toApiError(status: number, body: unknown, statusText = ''): ApiError {
  if (isRecord(body) && isRecord(body.error) && typeof body.error.code === 'string') {
    const { code, message, details } = body.error
    return new ApiError(status, code, typeof message === 'string' ? message : code, details)
  }
  if (isRecord(body) && typeof body.detail === 'string') {
    return new ApiError(status, `HTTP_${status}`, body.detail, body)
  }
  return new ApiError(
    status,
    `HTTP_${status}`,
    statusText || `Request failed with status ${status}`,
    body,
  )
}

/** Reads a failed Response into an ApiError, tolerating empty or non-JSON bodies. */
export async function parseErrorResponse(response: Response): Promise<ApiError> {
  let body: unknown = undefined
  const text = await response.text().catch(() => '')
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }
  return toApiError(response.status, body, response.statusText)
}

/** TanStack Query retry policy: never retry 4xx or aborted requests, retry others twice. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && (error.isClientError || error.code === CLIENT_ERROR.ABORTED)) {
    return false
  }
  return failureCount < 2
}
