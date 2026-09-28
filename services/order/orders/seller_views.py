"""Order HTTP API for sellers: their sub-orders, status changes and dashboard numbers.

Only the seller role gets in; sub-orders of other sellers answer 404.
"""

from datetime import timedelta
from typing import Any
from uuid import UUID

from django.db.models import QuerySet, Sum
from django.db.models.functions import Coalesce
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from contracts.enums import SubOrderStatus
from orders import fulfilment, stats
from orders.models import SubOrder
from orders.serializers import (
    SellerListFilterSerializer,
    SellerStatsSerializer,
    SellerSubOrderDetailSerializer,
    SellerSubOrderSerializer,
    SubOrderStatusChangeSerializer,
)
from orders.views import error_responses
from py_common.web.drf import IsSeller, current_user

TAG = "seller-orders"

SELLER_ERRORS = {"e401": "NOT_AUTHENTICATED", "e403": "PERMISSION_DENIED: seller role required"}
SUB_ORDER_ERRORS = {**SELLER_ERRORS, "e404": "NOT_FOUND: no such sub-order of this seller"}


def seller_id(request: Request) -> UUID:
    user = current_user(request)
    assert user is not None  # IsSeller ran first
    # The auth service issues seller ids equal to the user id; the header wins if present.
    return user.seller_id or user.user_id


def seller_sub_orders(seller: UUID) -> QuerySet[SubOrder]:
    """The seller's sub-orders with what the list needs, in two queries per page."""
    return (
        SubOrder.objects.filter(seller_id=seller)
        .select_related("order")
        .annotate(items_count=Coalesce(Sum("items__qty"), 0))
        .order_by("-created_at", "-id")
    )


def detail_response(seller: UUID, sub_order_id: UUID) -> Response:
    sub_order = (
        seller_sub_orders(seller).prefetch_related("items", "history").filter(id=sub_order_id)
    ).first()
    if sub_order is None:
        raise NotFound("Sub-order not found.")
    return Response(SellerSubOrderDetailSerializer(sub_order).data)


class SellerSubOrderListView(generics.ListAPIView[SubOrder]):
    permission_classes = (IsSeller,)
    serializer_class = SellerSubOrderSerializer

    def get_queryset(self) -> QuerySet[SubOrder]:
        if getattr(self, "swagger_fake_view", False):
            return SubOrder.objects.none()
        filters = self._filters()
        queryset = seller_sub_orders(seller_id(self.request))
        if filters.get("status"):
            queryset = queryset.filter(status__in=filters["status"])
        if "date_from" in filters:
            queryset = queryset.filter(created_at__gte=stats.day_start(filters["date_from"]))
        if "date_to" in filters:
            next_day = filters["date_to"] + timedelta(days=1)
            queryset = queryset.filter(created_at__lt=stats.day_start(next_day))
        return queryset

    def _filters(self) -> dict[str, Any]:
        params = self.request.query_params
        data: dict[str, Any] = {
            "status": [
                value.strip()
                for raw in params.getlist("status")
                for value in raw.split(",")
                if value.strip()
            ]
        }
        for name in ("date_from", "date_to"):
            if params.get(name):
                data[name] = params[name]
        body = SellerListFilterSerializer(data=data)
        body.is_valid(raise_exception=True)
        return dict(body.validated_data)

    @extend_schema(
        tags=[TAG],
        operation_id="seller_orders_list",
        summary="Sub-orders of the current seller, newest first",
        parameters=[
            OpenApiParameter(
                "status",
                OpenApiTypes.STR,
                many=True,
                enum=[status.value for status in SubOrderStatus],
                description="Repeat the parameter or pass a comma separated list.",
            ),
            OpenApiParameter(
                "date_from",
                OpenApiTypes.DATE,
                description="First day, inclusive (Asia/Tashkent).",
            ),
            OpenApiParameter(
                "date_to",
                OpenApiTypes.DATE,
                description="Last day, inclusive (Asia/Tashkent).",
            ),
        ],
        responses={
            200: SellerSubOrderSerializer(many=True),
            **error_responses(e400="VALIDATION_ERROR: unknown status or bad date", **SELLER_ERRORS),
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().get(request, *args, **kwargs)


class SellerSubOrderDetailView(APIView):
    permission_classes = (IsSeller,)

    @extend_schema(
        tags=[TAG],
        operation_id="seller_orders_retrieve",
        responses={200: SellerSubOrderDetailSerializer, **error_responses(**SUB_ORDER_ERRORS)},
    )
    def get(self, request: Request, sub_order_id: UUID) -> Response:
        return detail_response(seller_id(request), sub_order_id)


class SellerSubOrderStatusView(APIView):
    permission_classes = (IsSeller,)

    @extend_schema(
        tags=[TAG],
        operation_id="seller_orders_set_status",
        summary="Accept, ship, deliver or cancel a sub-order",
        description=(
            "Allowed: NEW -> ACCEPTED | CANCELLED_BY_SELLER, ACCEPTED -> SHIPPED | "
            "CANCELLED_BY_SELLER, SHIPPED -> DELIVERED. SHIPPED needs tracking_number, "
            "CANCELLED_BY_SELLER needs reason. The order moves to FULFILLING with the first "
            "shipment and to COMPLETED once every sub-order that was not cancelled is delivered."
        ),
        request=SubOrderStatusChangeSerializer,
        responses={
            200: SellerSubOrderDetailSerializer,
            **error_responses(
                e400="VALIDATION_ERROR: unknown status, missing tracking_number or reason",
                **SUB_ORDER_ERRORS,
                e409=(
                    "INVALID_TRANSITION with details {from, to}; ORDER_NOT_ACTIVE with "
                    "details {order_status}"
                ),
            ),
        },
    )
    def patch(self, request: Request, sub_order_id: UUID) -> Response:
        seller = seller_id(request)
        if not SubOrder.objects.filter(id=sub_order_id, seller_id=seller).exists():
            raise NotFound("Sub-order not found.")
        body = SubOrderStatusChangeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        fulfilment.change_status(
            seller,
            sub_order_id,
            SubOrderStatus(body.validated_data["status"]),
            tracking_number=body.validated_data["tracking_number"],
            reason=body.validated_data["reason"],
        )
        return detail_response(seller, sub_order_id)


class SellerStatsView(APIView):
    permission_classes = (IsSeller,)

    @extend_schema(
        tags=[TAG],
        operation_id="seller_orders_stats",
        summary="Dashboard numbers of the current seller",
        description=(
            "Days, ISO weeks and calendar months in Asia/Tashkent. Sub-orders cancelled by "
            "the seller are left out of orders/gross/net but counted in by_status. "
            "net = gross - commission. daily covers the last 30 days including today."
        ),
        responses={200: SellerStatsSerializer, **error_responses(**SELLER_ERRORS)},
    )
    def get(self, request: Request) -> Response:
        data = stats.seller_stats(seller_id(request))
        return Response(SellerStatsSerializer(data).data)
