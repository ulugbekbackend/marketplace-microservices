"""Transactional outbox and the consumer side idempotency table."""

from django.db import models
from django.db.models import Q


class Outbox(models.Model):
    """One event waiting to be published. Written in the transaction of the change it
    describes; a relay publishes it later (P4) and stamps ``published_at``."""

    id = models.BigAutoField(primary_key=True)
    event_id = models.UUIDField(unique=True)
    event_type = models.CharField(max_length=64)
    correlation_id = models.UUIDField()
    occurred_at = models.DateTimeField()
    version = models.PositiveSmallIntegerField(default=1)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("id",)
        indexes = (
            models.Index(
                fields=["id"],
                condition=Q(published_at__isnull=True),
                name="outbox_unpublished_idx",
            ),
        )

    def __str__(self) -> str:
        return f"{self.event_type} {self.event_id}"


class ProcessedEvent(models.Model):
    """Event ids already handled by a consumer: a redelivery is skipped."""

    event_id = models.UUIDField(primary_key=True)
    event_type = models.CharField(max_length=64)
    processed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.event_id)
