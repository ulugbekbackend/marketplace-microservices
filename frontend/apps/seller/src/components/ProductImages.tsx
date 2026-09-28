import { useDeleteProductImage, type SellerImage } from '@bozorcha/api-client'
import {
  Button,
  Dialog,
  IMAGE_MAX_BYTES,
  ImageUploader,
  useToast,
  type ImageRejection,
} from '@bozorcha/ui'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { mergeUploadItems, useImageUploads } from '../lib/useImageUploads'

const MAX_MB = IMAGE_MAX_BYTES / (1024 * 1024)

/**
 * Product photos: uploads need the product id (the presigned URL is bound to it), so a new
 * product has to be saved first. Saved images can be deleted after a confirmation; a failed
 * local upload is simply dropped.
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
  const { uploads, add, retry, settle, discard } = useImageUploads(productId)
  const remove = useDeleteProductImage()
  const [confirming, setConfirming] = useState<{ id: string; name: string } | null>(null)

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

  const onRemove = (id: string) => {
    const item = items.find((candidate) => candidate.id === id)
    if (!item) return
    if (images.some((image) => image.id === id)) setConfirming({ id, name: item.name })
    else discard(id)
  }

  const confirmDelete = () => {
    if (!confirming || !productId) return
    const { id, name } = confirming
    setConfirming(null)
    remove.mutate(
      { productId, imageId: id },
      {
        onSuccess: () => toast({ tone: 'success', title: t('images.deleted', { name }) }),
        onError: () =>
          toast({ tone: 'danger', title: t('images.deleteFailed'), description: name }),
      },
    )
  }

  return (
    <>
      <ImageUploader
        items={items}
        onFiles={add}
        onReject={onReject}
        onRetry={retry}
        onRemove={onRemove}
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
          remove: (name) => t('images.remove', { name }),
        }}
      />
      <Dialog
        open={confirming !== null}
        onClose={() => setConfirming(null)}
        title={t('images.deleteTitle')}
        description={t('images.deleteDescription', { name: confirming?.name ?? '' })}
        closeLabel={t('common.close')}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirming(null)}>
              {t('images.keep')}
            </Button>
            <Button variant="danger" onClick={confirmDelete}>
              {t('images.deleteConfirm')}
            </Button>
          </>
        }
      />
    </>
  )
}
