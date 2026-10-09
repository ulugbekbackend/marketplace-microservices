"""Service-to-service API (payment). Traefik routes only ``/api/orders``, so
``/internal/orders`` is reachable on the internal network only.

    GET /internal/orders/{id}/payable/  -> {payable, amount_tiyin, status, customer_id,
                                            reserved_until}

A provider may start charging an order only while its stock is held: RESERVED and before
``reserved_until``. A payment that completes later still lands on the late payment path
in ``saga.apply_payment``.
"""

from uuid import UUID

from django.urls import path
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from contracts.enums import OrderStatus
from orders.models import Order
from py_common.web.drf import ApiError


class OrderNotFound(ApiError):
    def __init__(self) -> None:
        super().__init__("NOT_FOUND", "Order not found.", status=404)


def is_payable(order: Order) -> bool:
    return (
        order.status == OrderStatus.RESERVED.value
        and order.reserved_until is not None
        and order.reserved_until > timezone.now()
    )


class OrderPayableView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(exclude=True)
    def get(self, request: Request, order_id: UUID) -> Response:
        order = Order.objects.filter(id=order_id).first()
        if order is None:
            raise OrderNotFound
        return Response(
            {
                "payable": is_payable(order),
                "amount_tiyin": order.total_tiyin,
                "status": order.status,
                "customer_id": str(order.customer_id),
                "reserved_until": order.reserved_until,
            }
        )


urlpatterns = [
    path("<uuid:order_id>/payable/", OrderPayableView.as_view(), name="internal-order-payable"),
]
