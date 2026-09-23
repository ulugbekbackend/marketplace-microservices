"""Background work of the catalog worker."""

import logging
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from celery import Task, shared_task
from django.conf import settings

from products import storage
from products.images import InvalidImageError, render_webp
from products.models import ImageStatus, ProductImage
from products.services import RenditionKeys, complete_image, fail_image

logger = logging.getLogger(__name__)

MISSING_OBJECT_CODES = {"NoSuchKey", "404", "NotFound"}
RETRY_DELAYS_SECONDS = (5, 30, 120)


def rendition_key(original_key: str, name: str) -> str:
    """products/<id>/<uuid>.jpg -> products/<id>/<uuid>_medium.webp"""
    stem = original_key.rpartition(".")[0]
    return f"{stem}_{name}.webp"


def _is_missing(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") in MISSING_OBJECT_CODES


@shared_task(bind=True, max_retries=len(RETRY_DELAYS_SECONDS), acks_late=True)
def process_product_image(self: Task, image_id: str) -> str:
    """Validate an uploaded original and store WebP renditions of it.

    Anything that is not a JPEG, PNG or WebP image ends as ``failed``; storage outages
    are retried and fail the image only when the retries are exhausted.
    """
    image = ProductImage.objects.filter(id=image_id).first()
    if image is None or image.status != ImageStatus.PROCESSING:
        return "skipped"
    image_uuid = UUID(image_id)

    try:
        data = storage.download(image.original_key, max_bytes=settings.IMAGE_MAX_UPLOAD_BYTES)
        if data is None:
            fail_image(image_uuid, "original is larger than allowed")
            return ImageStatus.FAILED.value
        try:
            renditions = render_webp(data)
        except InvalidImageError as exc:
            fail_image(image_uuid, str(exc))
            return ImageStatus.FAILED.value

        keys = {name: rendition_key(image.original_key, name) for name in renditions}
        for name, content in renditions.items():
            storage.upload(keys[name], content, "image/webp")
    except ClientError as exc:
        if _is_missing(exc):
            fail_image(image_uuid, "original was not uploaded")
            return ImageStatus.FAILED.value
        return _retry_or_fail(self, image_uuid, exc)
    except BotoCoreError as exc:
        return _retry_or_fail(self, image_uuid, exc)

    complete_image(
        image_uuid,
        RenditionKeys(thumb=keys["thumb"], medium=keys["medium"], large=keys["large"]),
    )
    return ImageStatus.READY.value


def _retry_or_fail(task: Task, image_id: UUID, exc: Exception) -> str:
    retries: int = task.request.retries
    if retries >= len(RETRY_DELAYS_SECONDS):
        logger.exception("image processing gave up", extra={"image_id": str(image_id)})
        fail_image(image_id, "storage unavailable")
        return ImageStatus.FAILED.value
    raise task.retry(exc=exc, countdown=RETRY_DELAYS_SECONDS[retries])
