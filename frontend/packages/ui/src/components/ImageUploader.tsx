import { CircleAlert, ImagePlus, RotateCw } from 'lucide-react'
import { useId, useRef, useState, type DragEvent, type ReactNode } from 'react'
import { cn } from '../lib/cn'
import { Spinner } from './Spinner'

export const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const
export const IMAGE_MAX_BYTES = 10 * 1024 * 1024

export type ImageRejectReason = 'type' | 'size'
export type ImageRejection = { file: File; reason: ImageRejectReason }

export type UploadStatus = 'uploading' | 'processing' | 'ready' | 'failed'

export type UploadItem = {
  id: string
  /** File name or a description, used as the image's alt text. */
  name: string
  /** Local object URL while uploading, the thumbnail once ready. */
  previewUrl: string | null
  status: UploadStatus
  /** 0..1 while uploading. */
  progress?: number
  /** Reason shown on a failed tile. */
  error?: ReactNode
  /** A failed tile offers retry unless this is false (e.g. the server rejected the image). */
  retryable?: boolean
}

export type ImageUploaderLabels = {
  /** Heading of the drop zone. */
  title: string
  /** Allowed types and size, e.g. "JPG, PNG yoki WEBP, 10 MB gacha". */
  hint: string
  browse: string
  /** Shown while a file is dragged over the zone. */
  dropHere: string
  /** Accessible name of the list of images. */
  list: string
  uploading: (percent: number) => string
  processing: string
  ready: string
  failed: string
  retry: string
}

export type ImageUploaderProps = {
  items: UploadItem[]
  /** Called with the files that passed validation. */
  onFiles: (files: File[]) => void
  /** Called with the files that did not (wrong type or too large). */
  onReject?: (rejections: ImageRejection[]) => void
  onRetry?: (id: string) => void
  accept?: readonly string[]
  maxBytes?: number
  multiple?: boolean
  disabled?: boolean
  /** Explains why uploads are disabled (e.g. "save the product first"). */
  disabledHint?: ReactNode
  labels: ImageUploaderLabels
  className?: string
}

/** Client-side check before any upload: allowed MIME type and size. */
export function validateImageFile(
  file: File,
  {
    accept = IMAGE_TYPES,
    maxBytes = IMAGE_MAX_BYTES,
  }: { accept?: readonly string[]; maxBytes?: number } = {},
): ImageRejectReason | null {
  if (!accept.includes(file.type)) return 'type'
  if (file.size > maxBytes) return 'size'
  return null
}

/** Drag and drop or pick images; each tile shows upload progress, processing and the result. */
export function ImageUploader({
  items,
  onFiles,
  onReject,
  onRetry,
  accept = IMAGE_TYPES,
  maxBytes = IMAGE_MAX_BYTES,
  multiple = true,
  disabled = false,
  disabledHint,
  labels,
  className,
}: ImageUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const hintId = useId()

  const take = (fileList: FileList | null) => {
    if (!fileList || disabled) return
    const files = Array.from(fileList).slice(0, multiple ? undefined : 1)
    const accepted: File[] = []
    const rejected: ImageRejection[] = []
    for (const file of files) {
      const reason = validateImageFile(file, { accept, maxBytes })
      if (reason) rejected.push({ file, reason })
      else accepted.push(file)
    }
    if (rejected.length) onReject?.(rejected)
    if (accepted.length) onFiles(accepted)
  }

  const onDragOver = (event: DragEvent<HTMLDivElement>) => {
    if (disabled) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
    setDragging(true)
  }

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    take(event.dataTransfer.files)
  }

  return (
    <div className={cn('flex flex-col gap-3', className)}>
      <div
        data-testid="image-dropzone"
        data-dragging={dragging || undefined}
        onDragOver={onDragOver}
        onDragEnter={onDragOver}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          'flex flex-col items-center gap-3 rounded-xl border-2 border-dashed border-border-strong bg-surface-2 px-4 py-6 text-center',
          'transition-colors duration-150 ease-out',
          dragging && 'border-primary bg-primary-soft',
          disabled && 'opacity-60',
        )}
      >
        <span
          aria-hidden="true"
          className="grid size-11 place-items-center rounded-full bg-surface text-primary"
        >
          <ImagePlus size={22} strokeWidth={1.75} />
        </span>
        <div className="flex flex-col gap-1">
          <p className="font-semibold text-text">{dragging ? labels.dropHere : labels.title}</p>
          <p id={hintId} className="text-sm text-text-muted">
            {disabled && disabledHint ? disabledHint : labels.hint}
          </p>
        </div>
        <button
          type="button"
          disabled={disabled}
          aria-describedby={hintId}
          onClick={() => inputRef.current?.click()}
          className="inline-flex h-10 items-center rounded-lg border border-border bg-surface px-4 text-sm font-semibold text-text transition-colors duration-150 ease-out hover:bg-surface-2 focus-ring disabled:cursor-not-allowed disabled:opacity-60"
        >
          {labels.browse}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={accept.join(',')}
          multiple={multiple}
          disabled={disabled}
          tabIndex={-1}
          aria-hidden="true"
          data-testid="image-input"
          className="sr-only"
          onChange={(event) => {
            take(event.target.files)
            event.target.value = ''
          }}
        />
      </div>

      {items.length > 0 && (
        <ul
          aria-label={labels.list}
          className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-5"
        >
          {items.map((item) => (
            <UploadTile key={item.id} item={item} labels={labels} onRetry={onRetry} />
          ))}
        </ul>
      )}
    </div>
  )
}

function UploadTile({
  item,
  labels,
  onRetry,
}: {
  item: UploadItem
  labels: ImageUploaderLabels
  onRetry?: (id: string) => void
}) {
  const percent = Math.round((item.progress ?? 0) * 100)
  const statusText =
    item.status === 'uploading'
      ? labels.uploading(percent)
      : item.status === 'processing'
        ? labels.processing
        : item.status === 'failed'
          ? labels.failed
          : labels.ready

  return (
    <li
      data-status={item.status}
      className="relative aspect-square overflow-hidden rounded-lg border border-border bg-surface-2"
    >
      {item.previewUrl ? (
        <img
          src={item.previewUrl}
          alt={item.name}
          className={cn(
            'size-full object-cover',
            item.status !== 'ready' && 'opacity-50 grayscale-[40%]',
          )}
        />
      ) : (
        <span className="sr-only">{item.name}</span>
      )}

      {item.status === 'ready' ? (
        <span className="sr-only">{statusText}</span>
      ) : (
        <div className="absolute inset-x-0 bottom-0 flex flex-col gap-1.5 bg-surface/90 p-2 text-xs font-medium text-text">
          {item.status === 'uploading' && (
            <div
              role="progressbar"
              aria-label={item.name}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={percent}
              className="h-1.5 overflow-hidden rounded-full bg-border"
            >
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-150 ease-out"
                style={{ width: `${percent}%` }}
              />
            </div>
          )}
          <p
            role="status"
            className={cn(
              'flex items-center gap-1.5 tabular',
              item.status === 'failed' && 'text-danger-ink',
            )}
          >
            {item.status === 'processing' && <Spinner className="size-3" />}
            {item.status === 'failed' && (
              <CircleAlert aria-hidden="true" size={14} strokeWidth={1.75} className="shrink-0" />
            )}
            <span className="truncate">
              {item.status === 'failed' && item.error ? item.error : statusText}
            </span>
          </p>
          {item.status === 'failed' && onRetry && item.retryable !== false && (
            <button
              type="button"
              onClick={() => onRetry(item.id)}
              className="inline-flex items-center gap-1 self-start rounded-md font-semibold text-primary hover:underline focus-ring"
            >
              <RotateCw aria-hidden="true" size={12} strokeWidth={2} />
              {labels.retry}
            </button>
          )}
        </div>
      )}
    </li>
  )
}
