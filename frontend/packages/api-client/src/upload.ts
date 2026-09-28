import { ApiError, CLIENT_ERROR } from './errors'

export type UploadOptions = {
  /** Presigned URL; the request goes straight to storage, not through the API. */
  url: string
  body: Blob
  method?: string
  /** Headers the presigned URL was signed with (e.g. `Content-Type`). */
  headers?: Record<string, string>
  /** Fraction uploaded, 0..1. */
  onProgress?: (fraction: number) => void
  signal?: AbortSignal
  /** Injected in tests; defaults to the browser's XMLHttpRequest. */
  createXhr?: () => XMLHttpRequest
}

/**
 * Uploads a file with progress events. `fetch` cannot report upload progress, so this uses XHR.
 * Rejects with an ApiError: `NETWORK_ERROR`, `ABORTED` or `HTTP_<status>` from storage.
 */
export function uploadWithProgress({
  url,
  body,
  method = 'PUT',
  headers = {},
  onProgress,
  signal,
  createXhr = () => new XMLHttpRequest(),
}: UploadOptions): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new ApiError(0, CLIENT_ERROR.ABORTED, 'Upload was aborted'))
      return
    }
    const xhr = createXhr()
    const onAbort = () => xhr.abort()
    const cleanup = () => signal?.removeEventListener('abort', onAbort)

    xhr.open(method, url)
    for (const [name, value] of Object.entries(headers)) xhr.setRequestHeader(name, value)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) onProgress?.(event.loaded / event.total)
    }
    xhr.onload = () => {
      cleanup()
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(1)
        resolve()
      } else {
        reject(new ApiError(xhr.status, `HTTP_${xhr.status}`, `Upload failed (${xhr.status})`))
      }
    }
    xhr.onerror = () => {
      cleanup()
      reject(new ApiError(0, CLIENT_ERROR.NETWORK, 'Upload failed'))
    }
    xhr.onabort = () => {
      cleanup()
      reject(new ApiError(0, CLIENT_ERROR.ABORTED, 'Upload was aborted'))
    }
    signal?.addEventListener('abort', onAbort)
    xhr.send(body)
  })
}
