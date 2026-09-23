"""Seller lifecycle driven by events from the auth service."""

import logging

from django.db import transaction

from contracts.enums import EventType
from contracts.events import EventEnvelope, SellerApproved
from messaging.outbox import mark_processed
from sellers.models import Seller
from slugs import unique_slug

logger = logging.getLogger(__name__)


def handle_seller_approved(envelope: EventEnvelope) -> bool:
    """Create (or refresh) the shop of an approved seller. Idempotent by event id.

    Returns True when the event was applied, False when it had been processed before.
    """
    if envelope.event_type is not EventType.SELLER_APPROVED:
        raise ValueError(f"expected {EventType.SELLER_APPROVED}, got {envelope.event_type}")
    payload = SellerApproved.model_validate(envelope.payload)

    with transaction.atomic():
        if not mark_processed(envelope):
            logger.info(
                "seller.approved already processed", extra={"event_id": str(envelope.event_id)}
            )
            return False

        seller = Seller.objects.select_for_update().filter(id=payload.user_id).first()
        if seller is None:
            Seller.objects.create(
                id=payload.user_id,
                user_id=payload.user_id,
                shop_name=payload.shop_name,
                slug=unique_slug(Seller, payload.shop_name, max_length=140),
                is_verified=True,
            )
        else:
            seller.shop_name = payload.shop_name
            seller.is_verified = True
            seller.save(update_fields=["shop_name", "is_verified"])
    return True
