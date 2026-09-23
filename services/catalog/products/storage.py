"""S3 (MinIO) access: presigned uploads for browsers, reads and writes for the worker."""

from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING
from uuid import UUID

import boto3
from botocore.config import Config
from django.conf import settings

from contracts.ids import uuid7

if TYPE_CHECKING:
    from types_boto3_s3.client import S3Client

IMAGE_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
IMAGE_CONTENT_TYPE_CHOICES = [(content_type, content_type) for content_type in IMAGE_EXTENSIONS]


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    upload_url: str
    key: str
    headers: dict[str, str]
    expires_in: int


@cache
def _client(endpoint_url: str, access_key: str, secret_key: str, region: str) -> "S3Client":
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def internal_client() -> "S3Client":
    """Client for server side reads and writes over the internal network."""
    return _client(
        settings.S3_ENDPOINT, settings.S3_ACCESS_KEY, settings.S3_SECRET_KEY, settings.S3_REGION
    )


def public_client() -> "S3Client":
    """Client used only to sign URLs for the browser-facing host (SigV4 signs the host)."""
    return _client(
        settings.S3_PUBLIC_ENDPOINT,
        settings.S3_ACCESS_KEY,
        settings.S3_SECRET_KEY,
        settings.S3_REGION,
    )


def product_prefix(product_id: UUID) -> str:
    return f"products/{product_id}/"


def new_original_key(product_id: UUID, content_type: str) -> str:
    return f"{product_prefix(product_id)}{uuid7()}.{IMAGE_EXTENSIONS[content_type]}"


def presign_upload(product_id: UUID, content_type: str, size: int) -> PresignedUpload:
    """A PUT URL bound to one key, one content type and the declared size."""
    key = new_original_key(product_id, content_type)
    ttl: int = settings.IMAGE_UPLOAD_URL_TTL_SECONDS
    url = public_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.S3_BUCKET,
            "Key": key,
            "ContentType": content_type,
            "ContentLength": size,
        },
        ExpiresIn=ttl,
        HttpMethod="PUT",
    )
    return PresignedUpload(
        upload_url=url, key=key, headers={"Content-Type": content_type}, expires_in=ttl
    )


def public_url(key: str) -> str | None:
    if not key:
        return None
    return f"{settings.S3_PUBLIC_ENDPOINT.rstrip('/')}/{settings.S3_BUCKET}/{key}"


def download(key: str, *, max_bytes: int) -> bytes | None:
    """Read an object; None when it is larger than ``max_bytes``."""
    response = internal_client().get_object(Bucket=settings.S3_BUCKET, Key=key)
    if response["ContentLength"] > max_bytes:
        response["Body"].close()
        return None
    data = response["Body"].read(max_bytes + 1)
    return None if len(data) > max_bytes else data


def upload(key: str, data: bytes, content_type: str) -> None:
    internal_client().put_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
        CacheControl="public, max-age=31536000, immutable",
    )
