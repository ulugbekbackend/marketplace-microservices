import type { ProductImage } from '@bozorcha/api-client'
import { cn } from '@bozorcha/ui'
import { ImageOff } from 'lucide-react'
import { useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { displayImages, largeSrc, thumbSrc } from '../lib/images'

export function Gallery({ images, title }: { images: ProductImage[]; title: string }) {
  const { t } = useTranslation()
  const sorted = useMemo(() => displayImages(images), [images])
  const [index, setIndex] = useState(0)
  const thumbRefs = useRef<Array<HTMLButtonElement | null>>([])
  const active = sorted[Math.min(index, sorted.length - 1)]

  if (!active) {
    return (
      <div className="grid aspect-square w-full place-items-center rounded-xl border border-border bg-surface-2 text-text-muted">
        <div className="flex flex-col items-center gap-2">
          <ImageOff aria-hidden="true" size={32} strokeWidth={1.75} />
          <span className="text-sm">{t('product.noImage')}</span>
        </div>
      </div>
    )
  }

  const onThumbKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    if (!delta) return
    event.preventDefault()
    const next = (index + delta + sorted.length) % sorted.length
    setIndex(next)
    thumbRefs.current[next]?.focus()
  }

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="overflow-hidden rounded-xl border border-border bg-surface">
        <img
          key={active.id}
          src={largeSrc(active) ?? undefined}
          srcSet={
            active.medium_url && active.large_url
              ? `${active.medium_url} 600w, ${active.large_url} 1200w`
              : undefined
          }
          sizes="(min-width: 1024px) 55vw, 100vw"
          alt={t('product.imageAlt', { title, index: index + 1 })}
          width={1200}
          height={1200}
          className="aspect-square w-full animate-fade-in object-contain"
        />
      </div>
      {sorted.length > 1 && (
        <div
          role="group"
          aria-label={t('product.gallery')}
          className="flex gap-2 overflow-x-auto pb-1 [scrollbar-width:thin]"
        >
          {sorted.map((image, i) => (
            <button
              key={image.id}
              ref={(node) => {
                thumbRefs.current[i] = node
              }}
              type="button"
              aria-label={t('product.showImage', { index: i + 1 })}
              aria-current={i === index ? 'true' : undefined}
              tabIndex={i === index ? 0 : -1}
              onClick={() => setIndex(i)}
              onKeyDown={onThumbKeyDown}
              className={cn(
                'size-16 shrink-0 overflow-hidden rounded-lg border-2 bg-surface-2 transition-colors duration-150 ease-out focus-ring sm:size-20',
                i === index ? 'border-primary' : 'border-transparent hover:border-border-strong',
              )}
            >
              <img
                src={thumbSrc(image) ?? undefined}
                alt=""
                loading="lazy"
                className="size-full object-cover"
              />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
