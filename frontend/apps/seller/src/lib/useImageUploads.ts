import {
  CLIENT_ERROR,
  isApiError,
  queryKeys,
  uploadWithProgress,
  useApi,
  type ImageContentType,
  type SellerImage,
  type SellerProductDetail,
} from '@bozorcha/api-client'
import type { UploadItem } from '@bozorcha/ui'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'

export type UploadErrorKey = 'network' | 'rejected' | 'storage' | 'unknown' | 'processingFailed'

type LocalUpload = {
  id: string
  file: File
  previewUrl: string
  status: 'uploading' | 'failed' | 'attached'
  progress: number
  error?: UploadErrorKey
  /** Server image id once attached; the local preview stands in while it is processed. */
  imageId?: string
}

/** Which message to show for a failed upload step. */
export function uploadErrorKey(error: unknown): UploadErrorKey {
  if (!isApiError(error)) return 'unknown'
  if (error.code === CLIENT_ERROR.NETWORK) return 'network'
  if (error.code.startsWith('HTTP_') && error.status >= 400 && error.status < 500) return 'storage'
  if (error.status === 400 || error.code === 'VALIDATION_ERROR') return 'rejected'
  return 'unknown'
}

let sequence = 0
const nextId = () => `upload-${Date.now()}-${++sequence}`

const createPreview = (file: File) =>
  typeof URL.createObjectURL === 'function' ? URL.createObjectURL(file) : ''
const revokePreview = (url: string) => {
  if (url && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(url)
}

/**
 * Upload flow for product images: presign -> PUT to storage with progress -> attach to the
 * product. The attached image is processed by a worker; the product query polls until it is
 * ready, and the local preview is shown meanwhile.
 */
export function useImageUploads(productId: string | null) {
  const { seller } = useApi()
  const queryClient = useQueryClient()
  const [uploads, setUploads] = useState<LocalUpload[]>([])
  const uploadsRef = useRef(uploads)
  useEffect(() => {
    uploadsRef.current = uploads
  }, [uploads])

  const patch = useCallback((id: string, change: Partial<LocalUpload>) => {
    setUploads((list) => list.map((item) => (item.id === id ? { ...item, ...change } : item)))
  }, [])

  const run = useCallback(
    async (upload: LocalUpload) => {
      if (!productId) return
      const { id, file } = upload
      try {
        const presign = await seller.presignUpload({
          product_id: productId,
          filename: file.name,
          content_type: file.type as ImageContentType,
          size: file.size,
        })
        await uploadWithProgress({
          url: presign.upload_url,
          method: presign.method || 'PUT',
          headers: presign.headers,
          body: file,
          onProgress: (progress) => patch(id, { progress }),
        })
        const image = await seller.attachImage(productId, { key: presign.key })
        patch(id, { status: 'attached', progress: 1, imageId: image.id })
        const key = queryKeys.sellerProduct(productId)
        queryClient.setQueryData<SellerProductDetail>(key, (old) =>
          old
            ? { ...old, images: [...old.images.filter((item) => item.id !== image.id), image] }
            : old,
        )
        void queryClient.invalidateQueries({ queryKey: key })
      } catch (error) {
        patch(id, { status: 'failed', error: uploadErrorKey(error) })
      }
    },
    [productId, seller, patch, queryClient],
  )

  const add = useCallback(
    (files: File[]) => {
      const created = files.map<LocalUpload>((file) => ({
        id: nextId(),
        file,
        previewUrl: createPreview(file),
        status: 'uploading',
        progress: 0,
      }))
      setUploads((list) => [...list, ...created])
      created.forEach((upload) => void run(upload))
    },
    [run],
  )

  const retry = useCallback(
    (id: string) => {
      const upload = uploadsRef.current.find((item) => item.id === id)
      if (!upload || upload.status !== 'failed') return
      patch(id, { status: 'uploading', progress: 0, error: undefined })
      void run({ ...upload, status: 'uploading', progress: 0 })
    },
    [patch, run],
  )

  // Revoke previews when leaving the page.
  useEffect(
    () => () => {
      uploadsRef.current.forEach((upload) => revokePreview(upload.previewUrl))
    },
    [],
  )

  /** Drops local previews once the server has a final result for the image. */
  const settle = useCallback((images: readonly SellerImage[]) => {
    const done = new Set(
      images.filter((image) => image.status !== 'processing').map((image) => image.id),
    )
    const finished = uploadsRef.current.filter((u) => u.imageId && done.has(u.imageId))
    if (!finished.length) return
    finished.forEach((upload) => revokePreview(upload.previewUrl))
    const ids = new Set(finished.map((upload) => upload.id))
    setUploads((list) => list.filter((upload) => !ids.has(upload.id)))
  }, [])

  /** Drops a local upload that failed (it never reached the product). */
  const discard = useCallback((id: string) => {
    const upload = uploadsRef.current.find((item) => item.id === id)
    if (!upload || upload.status !== 'failed') return
    revokePreview(upload.previewUrl)
    setUploads((list) => list.filter((item) => item.id !== id))
  }, [])

  return { uploads, add, retry, settle, discard }
}

/**
 * Server images first (by position), then files still uploading or failed. Every server image
 * can be deleted; a local upload only once it failed.
 */
export function mergeUploadItems(
  images: readonly SellerImage[],
  uploads: readonly LocalUpload[],
  labels: { imageAlt: (n: number) => string; error: (key: UploadErrorKey) => string },
): UploadItem[] {
  const previewByImage = new Map(
    uploads.filter((u) => u.imageId).map((u) => [u.imageId!, u.previewUrl]),
  )
  const serverIds = new Set(images.map((image) => image.id))
  const sorted = [...images].sort((a, b) => (a.position ?? 0) - (b.position ?? 0))
  const items: UploadItem[] = sorted.map((image, index) => {
    const status = image.status ?? 'processing'
    return {
      id: image.id,
      name: labels.imageAlt(index + 1),
      previewUrl:
        status === 'ready'
          ? (image.thumb_url ?? image.medium_url)
          : (previewByImage.get(image.id) ?? null),
      status,
      removable: true,
      ...(status === 'failed' ? { error: labels.error('processingFailed'), retryable: false } : {}),
    }
  })
  for (const upload of uploads) {
    if (upload.imageId && serverIds.has(upload.imageId)) continue
    items.push({
      id: upload.id,
      name: upload.file.name,
      previewUrl: upload.previewUrl || null,
      status: upload.status === 'attached' ? 'processing' : upload.status,
      progress: upload.progress,
      removable: upload.status === 'failed',
      ...(upload.error ? { error: labels.error(upload.error) } : {}),
    })
  }
  return items
}
