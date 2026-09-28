import type { SellerImage } from '@bozorcha/api-client'
import { IMAGE_MAX_BYTES, ImageUploader, useToast, type ImageRejection } from '@bozorcha/ui'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { mergeUploadItems, useImageUploads } from '../lib/useImageUploads'

const MAX_MB = IMAGE_MAX_BYTES / (1024 * 1024)

/**
 * Product photos: uploads need the product id (the presigned URL is bound to it), so a new
 * product has to be saved first.
 */
export function ProductImages({
  productId,
  images,
}: {
  productId: string | null
  images: readonly SellerImage[]
}) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const { uploads, add, retry, settle } = useImageUploads(productId)

  useEffect(() => settle(images), [images, settle])

  const onReject = (rejections: ImageRejection[]) => {
    for (const { file, reason } of rejections) {
      toast({
        tone: 'danger',
        title: file.name,
        description:
          reason === 'type' ? t('images.wrongType') : t('images.tooLarge', { max: MAX_MB }),
      })
    }
  }

  const items = mergeUploadItems(images, uploads, {
    imageAlt: (n) => t('images.alt', { n }),
    error: (key) => t(`images.errors.${key}`),
  })

  return (
    <ImageUploader
      items={items}
      onFiles={add}
      onReject={onReject}
      onRetry={retry}
      disabled={!productId}
      disabledHint={t('images.saveFirst')}
      labels={{
        title: t('images.title'),
        hint: t('images.hint', { max: MAX_MB }),
        browse: t('images.browse'),
        dropHere: t('images.dropHere'),
        list: t('images.list'),
        uploading: (percent) => t('images.uploading', { percent }),
        processing: t('images.processing'),
        ready: t('images.ready'),
        failed: t('images.failed'),
        retry: t('common.retry'),
      }}
    />
  )
}
