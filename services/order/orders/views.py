"""Order HTTP API for customers. Every route needs a signed-in user (any role may buy);
orders of other users answer 404."""

from typing import Any
from uuid import UUID

from django.conf import settings
from django.db.models import Count, QuerySet
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from contracts.enums import OrderStatus
from contracts.headers import IDEMPOTENCY_KEY
from orders import idempotency, services
from orders.models import Order
from orders.serializers import (
    CheckoutResultSerializer,
    CheckoutSerializer,
    ErrorSerializer,
    OrderDetailSerializer,
    OrderStatusSerializer,
    OrderSummarySerializer,
)
from py_common.web.drf import current_user

TAG = "orders"


def error_responses(**descriptions: str) -> dict[int, OpenApiResponse]:
    """OpenAPI error responses: ``error_responses(e409="CART_EMPTY, ...")``."""
    return {
        int(code.removeprefix("e")): OpenApiResponse(response=ErrorSerializer, description=text)
        for code, text in descriptions.items()
    }


COMMON_ERRORS = {"e401": "NOT_AUTHENTICATED"}
ORDER_ERRORS = {**COMMON_ERRORS, "e404": "NOT_FOUND: no such order of the current user"}


def customer_id(request: Request) -> UUID:
    user = current_user(request)
    assert user is not None  # IsAuthenticatedUser ran first
    return user.user_id


def own_order(request: Request, order_id: UUID) -> Order:
    try:
        return Order.objects.get(id=order_id, customer_id=customer_id(request))
    except Order.DoesNotExist as exc:
        raise NotFound("Order not found.") from exc


def detail_response(order_id: UUID, status_code: int = status.HTTP_200_OK) -> Response:
    order = Order.objects.prefetch_related(
        "items", "sub_orders", "sub_orders__history", "history"
    ).get(id=order_id)
    return Response(OrderDetailSerializer(order).data, status=status_code)


class OrderListView(generics.ListAPIView[Order]):
    serializer_class = OrderSummarySerializer

    def get_queryset(self) -> QuerySet[Order]:
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return (
            Order.objects.filter(customer_id=customer_id(self.request))
            .annotate(items_count=Count("items"))
            .order_by("-created_at", "-id")
        )

    @extend_schema(
        tags=[TAG],
        operation_id="orders_list",
        responses={200: OrderSummarySerializer(many=True), **error_responses(**COMMON_ERRORS)},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        overdue = Order.objects.filter(
            customer_id=customer_id(request),
            status=OrderStatus.RESERVED.value,
            reserved_until__lt=timezone.now(),
        ).values_list("id", flat=True)
        for order_id in list(overdue):
            services.expire_order(order_id)
        return super().get(request, *args, **kwargs)


class CheckoutView(APIView):
    @extend_schema(
        tags=[TAG],
        operation_id="orders_checkout",
        summary="Create an order from the cart",
        description=(
            "Snapshots current catalog prices, creates the order and reserves its stock. "
            "The answer carries the order id and its status (RESERVED, or CANCELLED when "
            "the stock could not be held); poll the status endpoint afterwards. "
            f"Retries with the same {IDEMPOTENCY_KEY} and body replay the first answer."
        ),
        parameters=[
            OpenApiParameter(
                IDEMPOTENCY_KEY,
                OpenApiTypes.STR,
                OpenApiParameter.HEADER,
                required=True,
                description="Unique per checkout attempt (e.g. a UUID), at most 255 characters.",
            )
        ],
        request=CheckoutSerializer,
        responses={
            202: CheckoutResultSerializer,
            **error_responses(
                e400="VALIDATION_ERROR, IDEMPOTENCY_KEY_REQUIRED, IDEMPOTENCY_KEY_INVALID",
                **COMMON_ERRORS,
                e409=(
                    "CART_EMPTY; ITEMS_UNAVAILABLE with details.items[{variant_id, reason "
                    "(not_found|inactive|out_of_stock), available}]; IDEMPOTENCY_KEY_REUSED; "
                    "IDEMPOTENCY_IN_PROGRESS"
                ),
                e503="SERVICE_UNAVAILABLE: cart, catalog or redis did not answer",
            ),
        },
    )
    def post(self, request: Request) -> Response:
        key = idempotency.require_key(request.headers.get(IDEMPOTENCY_KEY))
        user_id = customer_id(request)
        return idempotency.run_once(user_id, key, request.data, lambda: self._checkout(request))

    def _checkout(self, request: Request) -> Response:
        body = CheckoutSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        order = services.checkout(customer_id(request), dict(body.validated_data["address"]))
        return Response(
            {"order_id": str(order.id), "status": order.status}, status=status.HTTP_202_ACCEPTED
        )


class OrderDetailView(APIView):
    @extend_schema(
        tags=[TAG],
        operation_id="orders_retrieve",
        responses={200: OrderDetailSerializer, **error_responses(**ORDER_ERRORS)},
    )
    def get(self, request: Request, order_id: UUID) -> Response:
        order = own_order(request, order_id)
        services.expire_if_overdue(order)
        return detail_response(order.id)


class OrderStatusView(APIView):
    @extend_schema(
        tags=[TAG],
        operation_id="orders_status",
        summary="Order status for polling",
        responses={200: OrderStatusSerializer, **error_responses(**ORDER_ERRORS)},
    )
    def get(self, request: Request, order_id: UUID) -> Response:
        order = own_order(request, order_id)
        services.expire_if_overdue(order)
        return Response(OrderStatusSerializer(order).data)


class OrderCancelView(APIView):
    @extend_schema(
        tags=[TAG],
        operation_id="orders_cancel",
        request=None,
        responses={
            200: OrderDetailSerializer,
            **error_responses(**ORDER_ERRORS, e409="INVALID_TRANSITION: only PENDING or RESERVED"),
        },
    )
    def post(self, request: Request, order_id: UUID) -> Response:
        order = own_order(request, order_id)
        services.cancel_order(order.id)
        return detail_response(order.id)


class MockPayView(APIView):
    @extend_schema(
        tags=[TAG],
        operation_id="orders_pay_mock",
        summary="Pay an order without a provider (development only)",
        description="Exists only when PAYMENT_MOCK_ENABLED and DEBUG are on; 404 otherwise.",
        request=None,
        responses={
            200: OrderDetailSerializer,
            **error_responses(
                **ORDER_ERRORS,
                e409="INVALID_TRANSITION, ORDER_EXPIRED, NOT_RESERVED",
                e503="SERVICE_UNAVAILABLE: catalog did not answer",
            ),
        },
    )
    def post(self, request: Request, order_id: UUID) -> Response:
        if not (settings.PAYMENT_MOCK_ENABLED and settings.DEBUG):
            raise NotFound()
        order = own_order(request, order_id)
        services.mark_paid(order.id)
        return detail_response(order.id)
