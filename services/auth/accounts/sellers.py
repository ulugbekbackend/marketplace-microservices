"""Seller onboarding: a customer applies, an admin approves or rejects.

Approval changes the role and writes the ``seller.approved`` outbox row in one transaction,
so the event exists if and only if the promotion committed.
"""

from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import ApplicationStatus, Outbox, Role, SellerApplication, User
from contracts.events import EventEnvelope, SellerApproved, build_event
from py_common.web.drf import ApiError

PRODUCER = "auth"


def _get_user(user_id: UUID, *, lock: bool = False) -> User:
    queryset = User.objects.select_for_update() if lock else User.objects.all()
    user = queryset.filter(pk=user_id, is_active=True).first()
    if user is None:
        raise ApiError("USER_NOT_FOUND", "User not found.", status=404)
    return user


def apply(user_id: UUID, *, shop_name: str, inn: str, description: str) -> SellerApplication:
    with transaction.atomic():
        user = _get_user(user_id, lock=True)
        if user.role != Role.CUSTOMER:
            raise ApiError("ALREADY_SELLER", "This account is already a seller.", status=409)
        if SellerApplication.objects.filter(user=user, status=ApplicationStatus.PENDING).exists():
            raise _pending_error()
        try:
            with transaction.atomic():
                return SellerApplication.objects.create(
                    user=user, shop_name=shop_name, inn=inn, description=description
                )
        except IntegrityError as exc:  # the partial unique index caught a concurrent apply
            raise _pending_error() from exc


def _pending_error() -> ApiError:
    return ApiError(
        "APPLICATION_PENDING", "An application is already waiting for review.", status=409
    )


def latest_application(user_id: UUID) -> SellerApplication | None:
    return SellerApplication.objects.filter(user_id=user_id).order_by("-created_at").first()


def _lock_pending(application_id: UUID) -> SellerApplication:
    application = SellerApplication.objects.select_for_update().filter(pk=application_id).first()
    if application is None:
        raise ApiError("NOT_FOUND", "Application not found.", status=404)
    if application.status != ApplicationStatus.PENDING:
        raise ApiError(
            "ALREADY_REVIEWED",
            "This application has already been reviewed.",
            status=409,
            details={"status": application.status},
        )
    return application


def write_event(envelope: EventEnvelope) -> Outbox:
    """Store an event for the publisher; must run inside the business transaction."""
    return Outbox.objects.create(
        event_id=envelope.event_id,
        event_type=envelope.event_type.value,
        payload=envelope.model_dump(mode="json"),
        created_at=envelope.occurred_at,
    )


def approve(application_id: UUID, *, reviewer_id: UUID) -> SellerApplication:
    """Promote the applicant to seller and record ``seller.approved``, all or nothing."""
    with transaction.atomic():
        reviewer = _get_user(reviewer_id)
        application = _lock_pending(application_id)
        user = _get_user(application.user_id, lock=True)
        now = timezone.now()

        user.role = Role.SELLER
        user.save(update_fields=["role"])
        write_event(
            build_event(
                SellerApproved(user_id=user.id, shop_name=application.shop_name),
                producer=PRODUCER,
                correlation_id=user.id,
                occurred_at=now,
            )
        )
        application.status = ApplicationStatus.APPROVED
        application.reviewed_by = reviewer
        application.reviewed_at = now
        application.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        return application


def reject(application_id: UUID, *, reviewer_id: UUID) -> SellerApplication:
    with transaction.atomic():
        reviewer = _get_user(reviewer_id)
        application = _lock_pending(application_id)
        application.status = ApplicationStatus.REJECTED
        application.reviewed_by = reviewer
        application.reviewed_at = timezone.now()
        application.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        return application
