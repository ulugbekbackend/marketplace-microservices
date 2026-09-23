import type { ProductImage } from '@bozorcha/api-client'

/** Image sizes are null while the resize worker is still processing an upload. */
export const largeSrc = (image: ProductImage) =>
  image.large_url ?? image.medium_url ?? image.thumb_url

export const thumbSrc = (image: ProductImage) =>
  image.thumb_url ?? image.medium_url ?? image.large_url

/** Images that have at least one rendition, in display order. */
export function displayImages(images: ProductImage[]): ProductImage[] {
  return images
    .filter((image) => largeSrc(image) !== null)
    .sort((a, b) => (a.position ?? 0) - (b.position ?? 0))
}
