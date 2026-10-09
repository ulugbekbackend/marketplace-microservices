"""Customer facing payment API: start a payment, and the development mock payment."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.deps import Orders, Sessions, SettingsDep
from app.schemas import InitRequest, InitResponse, MockPayResponse
from app.services import checkout, payments
from app.services.orders import OrderClient, OrderUnavailableError, Payable
from contracts.enums import PaymentProvider
from contracts.ids import uuid7
from py_common.auth import CurrentUser
from py_common.web.fastapi import ApiError, required_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])

User = Annotated[CurrentUser, Depends(required_user)]

ERRORS = {
    404: {"description": "NOT_FOUND: no such order of this customer"},
    409: {"description": "ORDER_NOT_PAYABLE / PAYMENT_IN_PROGRESS"},
    503: {"description": "ORDER_SERVICE_UNAVAILABLE"},
}


async def owned_payable_order(orders: OrderClient, order_id: UUID, user: CurrentUser) -> Payable:
    try:
        order = await orders.payable(order_id)
    except OrderUnavailableError as exc:
        logger.warning("order service unavailable", exc_info=True)
        raise ApiError(
            "ORDER_SERVICE_UNAVAILABLE", "Orders are unavailable, try again.", status=503
        ) from exc
    if order is None or order.customer_id != user.user_id:
        raise ApiError("NOT_FOUND", "Order not found.", status=404)
    if not order.payable:
        raise ApiError(
            "ORDER_NOT_PAYABLE",
            "This order cannot be paid.",
            status=409,
            details={"status": order.status},
        )
    return order


@router.post(
    "/{order_id}/init/",
    response_model=InitResponse,
    operation_id="payments_init",
    responses=ERRORS,  # type: ignore[arg-type]
)
async def init_payment(
    order_id: UUID, body: InitRequest, user: User, orders: Orders, settings: SettingsDep
) -> InitResponse:
    """Where to send the customer to pay a RESERVED order with the chosen provider."""
    order = await owned_payable_order(orders, order_id, user)
    provider = PaymentProvider(body.provider)
    return InitResponse(
        redirect_url=checkout.redirect_url(settings, provider, order_id, order.amount_tiyin)
    )


@router.post(
    "/mock/{order_id}/pay",
    response_model=MockPayResponse,
    operation_id="payments_mock_pay",
    responses=ERRORS,  # type: ignore[arg-type]
)
async def mock_pay(
    order_id: UUID, user: User, orders: Orders, sessions: Sessions, settings: SettingsDep
) -> MockPayResponse:
    """Development only (PAYMENT_MOCK_ENABLED): pay at once through the real
    ``payment.paid`` path. 404 when disabled."""
    if not settings.mock_enabled:
        raise ApiError("NOT_FOUND", "Not found.", status=404)
    order = await owned_payable_order(orders, order_id, user)
    async with sessions.begin() as session:
        if await payments.active_for_order(session, order_id) is not None:
            raise ApiError(
                "PAYMENT_IN_PROGRESS", "Another payment of this order is in progress.", status=409
            )
        now = payments.utcnow()
        transaction = payments.create(
            session,
            order_id=order_id,
            provider=PaymentProvider.MOCK,
            external_id=str(uuid7()),
            amount_tiyin=order.amount_tiyin,
            now=now,
        )
        payments.perform(session, transaction, now=now)
    return MockPayResponse(
        transaction_id=transaction.id, order_id=order_id, amount_tiyin=transaction.amount_tiyin
    )
