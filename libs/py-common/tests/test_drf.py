"""DRF adapter: gateway authentication, role permissions, error shape and pagination."""

from typing import Any
from uuid import uuid4

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        DEBUG=False,
        SECRET_KEY="tests",
        ALLOWED_HOSTS=["*"],
        INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth", "rest_framework"],
        DATABASES={},
        ROOT_URLCONF=__name__,
        REST_FRAMEWORK={
            "DEFAULT_AUTHENTICATION_CLASSES": ["py_common.web.drf.GatewayAuthentication"],
            "DEFAULT_PERMISSION_CLASSES": [],
            "UNAUTHENTICATED_USER": None,
            "EXCEPTION_HANDLER": "py_common.web.drf.exception_handler",
        },
    )
    django.setup()

import pytest
from django.http import Http404
from rest_framework import serializers
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from py_common.web.drf import (
    ApiError,
    IsAdmin,
    IsAuthenticatedUser,
    IsSeller,
    PagePagination,
    current_user,
)

urlpatterns: list[Any] = []
factory = APIRequestFactory()


def seller_headers() -> dict[str, Any]:
    return {
        "HTTP_X_USER_ID": str(uuid4()),
        "HTTP_X_USER_ROLE": "seller",
        "HTTP_X_SELLER_ID": str(uuid4()),
    }


def customer_headers() -> dict[str, Any]:
    return {"HTTP_X_USER_ID": str(uuid4()), "HTTP_X_USER_ROLE": "customer"}


class WhoAmI(APIView):
    def get(self, request: Request) -> Response:
        user = current_user(request)
        return Response({"user_id": str(user.user_id) if user else None})


class Private(APIView):
    permission_classes: tuple[type[BasePermission], ...] = (IsAuthenticatedUser,)

    def get(self, request: Request) -> Response:
        return Response({"ok": True})


class SellerOnly(Private):
    permission_classes = (IsSeller,)


class AdminOnly(Private):
    permission_classes = (IsAdmin,)


class NumberSerializer(serializers.Serializer[Any]):
    qty = serializers.IntegerField(min_value=1)


class Failing(APIView):
    def post(self, request: Request) -> Response:
        kind = request.data.get("kind")
        if kind == "business":
            raise ApiError("OUT_OF_STOCK", "Not enough stock.", status=409, details={"left": 2})
        if kind == "missing":
            raise Http404
        NumberSerializer(data=request.data).is_valid(raise_exception=True)
        return Response({"ok": True})


class Listing(APIView):
    def get(self, request: Request) -> Response:
        paginator = PagePagination()
        items: Any = list(range(45))
        page = paginator.paginate_queryset(items, request, view=self)
        return paginator.get_paginated_response(page)


def test_anonymous_request_has_no_user() -> None:
    response = WhoAmI.as_view()(factory.get("/"))
    assert response.data == {"user_id": None}


def test_gateway_headers_become_the_user() -> None:
    headers = customer_headers()
    response = WhoAmI.as_view()(factory.get("/", **headers))
    assert response.data == {"user_id": headers["HTTP_X_USER_ID"]}


def test_private_endpoint_rejects_anonymous_with_401() -> None:
    response = Private.as_view()(factory.get("/"))
    assert response.status_code == 401
    assert response.data["error"]["code"] == "NOT_AUTHENTICATED"
    assert response["WWW-Authenticate"] == "Bearer"


def test_malformed_identity_is_rejected() -> None:
    request = factory.get("/", HTTP_X_USER_ID="nope", HTTP_X_USER_ROLE="customer")
    response = Private.as_view()(request)
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("view", "headers", "expected"),
    [
        (SellerOnly, seller_headers, 200),
        (SellerOnly, customer_headers, 403),
        (AdminOnly, seller_headers, 403),
    ],
)
def test_role_permissions(view: type[APIView], headers: Any, expected: int) -> None:
    response = view.as_view()(factory.get("/", **headers()))
    assert response.status_code == expected
    if expected == 403:
        assert response.data["error"]["code"] == "PERMISSION_DENIED"


def test_business_error_shape() -> None:
    response = Failing.as_view()(factory.post("/", {"kind": "business"}, format="json"))
    assert response.status_code == 409
    assert response.data == {
        "error": {"code": "OUT_OF_STOCK", "message": "Not enough stock.", "details": {"left": 2}}
    }


def test_validation_error_shape() -> None:
    response = Failing.as_view()(factory.post("/", {"qty": 0}, format="json"))
    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    assert "qty" in response.data["error"]["details"]


def test_not_found_shape() -> None:
    response = Failing.as_view()(factory.post("/", {"kind": "missing"}, format="json"))
    assert response.status_code == 404
    assert response.data["error"]["code"] == "NOT_FOUND"


def test_pagination_shape() -> None:
    response = Listing.as_view()(factory.get("/", {"page": 2, "page_size": 20}))
    assert response.data["items"] == list(range(20, 40))
    assert response.data["total"] == 45
    assert response.data["page"] == 2
    assert response.data["page_size"] == 20


def test_page_size_is_capped_at_100() -> None:
    response = Listing.as_view()(factory.get("/", {"page_size": 500}))
    assert response.data["page_size"] == 100
