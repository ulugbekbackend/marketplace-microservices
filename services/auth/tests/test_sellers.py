import threading
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import QuerySet
from rest_framework.test import APIClient

from accounts import sellers
from accounts.models import ApplicationStatus, Outbox, Role, SellerApplication, User
from contracts.enums import EventType
from contracts.events import EventEnvelope, SellerApproved, parse_payload
from py_common.web.drf import ApiError
from tests.factories import make_application, make_user

pytestmark = pytest.mark.django_db

APPLY = "/api/auth/seller/apply/"
MINE = "/api/auth/seller/application/"
ADMIN_LIST = "/api/auth/admin/seller-applications/"
ClientFor = Callable[[User], APIClient]

BODY = {"shop_name": "Silk Road", "inn": "123456789", "description": "Scarves"}


def approve_url(application_id: UUID) -> str:
    return f"{ADMIN_LIST}{application_id}/approve/"


def reject_url(application_id: UUID) -> str:
    return f"{ADMIN_LIST}{application_id}/reject/"


# --- applying -----------------------------------------------------------------------------


def test_customer_applies(client_for: ClientFor, customer: User) -> None:
    response = client_for(customer).post(APPLY, BODY, format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["shop_name"] == "Silk Road"
    assert body["reviewed_at"] is None
    assert SellerApplication.objects.get(pk=body["id"]).user == customer


def test_description_is_optional(client_for: ClientFor, customer: User) -> None:
    body = {"shop_name": "Silk Road", "inn": "123456789"}

    assert client_for(customer).post(APPLY, body, format="json").status_code == 201


def test_second_application_while_pending_is_409(client_for: ClientFor, customer: User) -> None:
    client = client_for(customer)
    client.post(APPLY, BODY, format="json")

    response = client.post(APPLY, BODY, format="json")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPLICATION_PENDING"
    assert SellerApplication.objects.filter(user=customer).count() == 1


def test_may_apply_again_after_rejection(client_for: ClientFor, customer: User) -> None:
    make_application(user=customer, status=ApplicationStatus.REJECTED)

    assert client_for(customer).post(APPLY, BODY, format="json").status_code == 201


def test_seller_cannot_apply(client_for: ClientFor, seller: User) -> None:
    response = client_for(seller).post(APPLY, BODY, format="json")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_SELLER"


@pytest.mark.parametrize(
    "body",
    [
        {**BODY, "inn": "12345"},
        {**BODY, "inn": "12345678a"},
        {**BODY, "shop_name": ""},
        {"inn": "123456789"},
    ],
)
def test_invalid_application_is_400(
    client_for: ClientFor, customer: User, body: dict[str, str]
) -> None:
    response = client_for(customer).post(APPLY, body, format="json")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_anonymous_cannot_apply(api: APIClient) -> None:
    assert api.post(APPLY, BODY, format="json").status_code == 401


def test_database_allows_one_pending_application_per_user(customer: User) -> None:
    make_application(user=customer)

    with pytest.raises(IntegrityError), transaction.atomic():
        make_application(user=customer)


def test_concurrent_apply_maps_the_constraint_to_409(
    customer: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If a parallel request inserted first, the unique index answers and we return 409."""
    make_application(user=customer)
    real_filter = SellerApplication.objects.filter

    def blind_filter(*args: Any, **kwargs: Any) -> QuerySet[SellerApplication]:
        return real_filter(pk=uuid4()) if kwargs.get("status") else real_filter(*args, **kwargs)

    monkeypatch.setattr(SellerApplication.objects, "filter", blind_filter)

    with pytest.raises(ApiError) as caught:
        sellers.apply(customer.id, shop_name="X", inn="123456789", description="")
    assert caught.value.error_code == "APPLICATION_PENDING"


# --- the caller's application -----------------------------------------------------------


def test_no_application_is_404(client_for: ClientFor, customer: User) -> None:
    response = client_for(customer).get(MINE)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_latest_application_is_returned(client_for: ClientFor, customer: User) -> None:
    make_application(user=customer, status=ApplicationStatus.REJECTED)
    latest = make_application(user=customer)
    make_application()  # someone else's

    response = client_for(customer).get(MINE)

    assert response.status_code == 200
    assert response.json()["id"] == str(latest.id)


# --- admin: list ------------------------------------------------------------------------


def test_admin_lists_applications_paginated(client_for: ClientFor, admin_user: User) -> None:
    pending = [make_application() for _ in range(3)]
    make_application(status=ApplicationStatus.REJECTED)

    response = client_for(admin_user).get(ADMIN_LIST, {"status": "pending", "page_size": "2"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert [item["id"] for item in body["items"]] == [str(a.id) for a in pending[:2]]
    assert body["items"][0]["user"]["phone"] == pending[0].user.phone


def test_admin_list_without_filter_returns_all(client_for: ClientFor, admin_user: User) -> None:
    make_application()
    make_application(status=ApplicationStatus.APPROVED)

    assert client_for(admin_user).get(ADMIN_LIST).json()["total"] == 2


def test_admin_list_rejects_unknown_status(client_for: ClientFor, admin_user: User) -> None:
    response = client_for(admin_user).get(ADMIN_LIST, {"status": "maybe"})

    assert response.status_code == 400


# --- admin: role checks -------------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.CUSTOMER, Role.SELLER])
def test_non_admins_get_403(client_for: ClientFor, role: Role) -> None:
    client = client_for(make_user(role=role))
    application = make_application()

    for response in (
        client.get(ADMIN_LIST),
        client.post(approve_url(application.id)),
        client.post(reject_url(application.id)),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_anonymous_gets_401_on_admin_endpoints(api: APIClient) -> None:
    application = make_application()

    for response in (
        api.get(ADMIN_LIST),
        api.post(approve_url(application.id)),
        api.post(reject_url(application.id)),
    ):
        assert response.status_code == 401


# --- admin: approve / reject --------------------------------------------------------------


def test_approve_promotes_and_writes_the_event(client_for: ClientFor, admin_user: User) -> None:
    application = make_application(shop_name="Silk Road")
    applicant = application.user

    response = client_for(admin_user).post(approve_url(application.id))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] == str(admin_user.id)
    assert body["reviewed_at"] is not None
    applicant.refresh_from_db()
    assert applicant.role == Role.SELLER

    row = Outbox.objects.get()
    assert row.event_type == "seller.approved"
    assert row.published_at is None
    envelope = EventEnvelope.model_validate(row.payload)
    assert envelope.event_id == row.event_id
    assert envelope.event_type is EventType.SELLER_APPROVED
    assert envelope.producer == "auth"
    assert envelope.correlation_id == applicant.id
    assert parse_payload(envelope) == SellerApproved(user_id=applicant.id, shop_name="Silk Road")


def test_approving_twice_is_409(client_for: ClientFor, admin_user: User) -> None:
    application = make_application()
    client = client_for(admin_user)
    client.post(approve_url(application.id))

    response = client.post(approve_url(application.id))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_REVIEWED"
    assert Outbox.objects.count() == 1


def test_reject(client_for: ClientFor, admin_user: User) -> None:
    application = make_application()

    response = client_for(admin_user).post(reject_url(application.id))

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    application.refresh_from_db()
    assert application.reviewed_by == admin_user
    assert application.user.role == Role.CUSTOMER
    assert not Outbox.objects.exists()


def test_reviewed_application_cannot_be_rejected(client_for: ClientFor, admin_user: User) -> None:
    application = make_application(status=ApplicationStatus.APPROVED)

    response = client_for(admin_user).post(reject_url(application.id))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_REVIEWED"


def test_unknown_application_is_404(client_for: ClientFor, admin_user: User) -> None:
    client = client_for(admin_user)

    assert client.post(approve_url(uuid4())).status_code == 404
    assert client.post(reject_url(uuid4())).status_code == 404


def test_reviewer_must_exist(api: APIClient) -> None:
    application = make_application()

    response = api.post(
        approve_url(application.id), HTTP_X_USER_ID=str(uuid4()), HTTP_X_USER_ROLE="admin"
    )

    assert response.status_code == 404
    application.refresh_from_db()
    assert application.status == ApplicationStatus.PENDING


def test_failure_mid_approval_rolls_back_role_and_event(
    admin_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The outbox row is written before the application is saved; a crash there undoes all."""
    application = make_application()

    def crash(*args: object, **kwargs: object) -> None:
        raise RuntimeError("database went away")

    monkeypatch.setattr(SellerApplication, "save", crash)

    with pytest.raises(RuntimeError):
        sellers.approve(application.id, reviewer_id=admin_user.id)

    monkeypatch.undo()
    assert not Outbox.objects.exists()
    application.refresh_from_db()
    assert application.status == ApplicationStatus.PENDING
    assert User.objects.get(pk=application.user_id).role == Role.CUSTOMER


def test_failing_event_write_leaves_the_user_a_customer(
    admin_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = make_application()

    def crash(*args: object, **kwargs: object) -> None:
        raise RuntimeError("outbox insert failed")

    monkeypatch.setattr(sellers, "write_event", crash)

    with pytest.raises(RuntimeError):
        sellers.approve(application.id, reviewer_id=admin_user.id)

    assert User.objects.get(pk=application.user_id).role == Role.CUSTOMER


@pytest.mark.django_db(transaction=True)
def test_concurrent_approvals_write_one_event() -> None:
    admin = make_user(role=Role.ADMIN)
    application = make_application()
    barrier = threading.Barrier(3)
    results: list[str] = []

    def review() -> None:
        try:
            barrier.wait()
            sellers.approve(application.id, reviewer_id=admin.id)
            results.append("ok")
        except ApiError as exc:
            results.append(exc.error_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=review) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == ["ALREADY_REVIEWED", "ALREADY_REVIEWED", "ok"]
    assert Outbox.objects.count() == 1
