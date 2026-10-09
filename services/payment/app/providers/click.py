"""Click SHOP API: Click posts form data to ``prepare`` (action=0) and then ``complete``
(action=1); we answer JSON with ``error`` 0 or a negative code.

    sign_string = md5(click_trans_id + service_id + SECRET_KEY + merchant_trans_id
                      [+ merchant_prepare_id] + amount + action + sign_time)

``merchant_trans_id`` is our order id, ``amount`` is in so'm with decimals.
"""

import hashlib
import hmac
import logging
from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.metrics import PAYMENT_ERRORS
from app.models import TransactionState
from app.services import payments
from app.services.orders import OrderClient, OrderUnavailableError
from contracts.enums import OrderStatus, PaymentProvider
from contracts.money import som_to_tiyin

logger = logging.getLogger(__name__)

ACTION_PREPARE = 0
ACTION_COMPLETE = 1

SUCCESS = 0
SIGN_FAILED = -1
WRONG_AMOUNT = -2
ACTION_NOT_FOUND = -3
ALREADY_PAID = -4
ORDER_NOT_FOUND = -5
TRANSACTION_NOT_FOUND = -6
BAD_REQUEST = -8
TRANSACTION_CANCELLED = -9

NOTES = {
    SUCCESS: "Success",
    SIGN_FAILED: "SIGN CHECK FAILED!",
    WRONG_AMOUNT: "Incorrect parameter amount",
    ACTION_NOT_FOUND: "Action not found",
    ALREADY_PAID: "Already paid",
    ORDER_NOT_FOUND: "Order not found",
    TRANSACTION_NOT_FOUND: "Transaction does not exist",
    BAD_REQUEST: "Error in request from click",
    TRANSACTION_CANCELLED: "Transaction cancelled",
}

PAID_STATUSES = {
    OrderStatus.PAID.value,
    OrderStatus.FULFILLING.value,
    OrderStatus.COMPLETED.value,
}

PREPARE_FIELDS = (
    "click_trans_id",
    "service_id",
    "merchant_trans_id",
    "amount",
    "action",
    "error",
    "sign_time",
    "sign_string",
)


class ClickError(Exception):
    def __init__(self, code: int, note: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.note = note or NOTES[code]


def sign(params: Mapping[str, str], secret_key: str, *, with_prepare_id: bool) -> str:
    parts = [
        params.get("click_trans_id", ""),
        params.get("service_id", ""),
        secret_key,
        params.get("merchant_trans_id", ""),
    ]
    if with_prepare_id:
        parts.append(params.get("merchant_prepare_id", ""))
    parts += [params.get("amount", ""), params.get("action", ""), params.get("sign_time", "")]
    return hashlib.md5("".join(parts).encode()).hexdigest()


class ClickShop:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        orders: OrderClient,
        *,
        service_id: str,
        secret_key: str,
        clock: Callable[[], datetime] = payments.utcnow,
    ) -> None:
        self._sessions = sessions
        self._orders = orders
        self._service_id = service_id
        self._secret_key = secret_key
        self._clock = clock

    async def prepare(self, params: Mapping[str, str]) -> dict[str, Any]:
        answer: dict[str, Any] = _echo(params, "merchant_prepare_id")
        try:
            answer["merchant_prepare_id"] = await self._prepare(params)
        except ClickError as error:
            return _with_error(answer, error)
        return _with_error(answer, None)

    async def complete(self, params: Mapping[str, str]) -> dict[str, Any]:
        answer: dict[str, Any] = _echo(params, "merchant_confirm_id")
        try:
            answer["merchant_confirm_id"] = await self._complete(params)
        except ClickError as error:
            return _with_error(answer, error)
        return _with_error(answer, None)

    # --- steps --------------------------------------------------------------------------

    async def _prepare(self, params: Mapping[str, str]) -> int:
        self._verify(params, PREPARE_FIELDS, action=ACTION_PREPARE, with_prepare_id=False)
        order_id = _order_id(params)
        amount = _amount(params)
        external_id = params["click_trans_id"]

        existing = await self._existing(external_id)
        if existing is not None:
            return existing

        try:
            order = await self._orders.payable(order_id)
        except OrderUnavailableError:
            logger.warning("order service unavailable for click", exc_info=True)
            raise ClickError(BAD_REQUEST, "Order service unavailable") from None
        if order is None:
            raise ClickError(ORDER_NOT_FOUND)
        if amount != order.amount_tiyin:
            raise ClickError(WRONG_AMOUNT)
        if order.status in PAID_STATUSES:
            raise ClickError(ALREADY_PAID)
        if not order.payable:
            raise ClickError(TRANSACTION_CANCELLED, "Order cannot be paid")

        try:
            async with self._sessions.begin() as session:
                if await payments.active_for_order(session, order_id) is not None:
                    raise ClickError(TRANSACTION_CANCELLED, "Order has a pending transaction")
                transaction = payments.create(
                    session,
                    order_id=order_id,
                    provider=PaymentProvider.CLICK,
                    external_id=external_id,
                    amount_tiyin=amount,
                    now=self._clock(),
                )
        except IntegrityError:
            existing = await self._existing(external_id)
            if existing is not None:
                return existing
            raise ClickError(TRANSACTION_CANCELLED, "Order has a pending transaction") from None
        return transaction.number

    async def _complete(self, params: Mapping[str, str]) -> int:
        self._verify(
            params,
            (*PREPARE_FIELDS, "merchant_prepare_id"),
            action=ACTION_COMPLETE,
            with_prepare_id=True,
        )
        order_id = _order_id(params)
        amount = _amount(params)
        click_error = _int(params, "error")
        prepare_id = _int(params, "merchant_prepare_id")
        cancelled = False
        async with self._sessions.begin() as session:
            transaction = await payments.lock(
                session, PaymentProvider.CLICK, params["click_trans_id"]
            )
            if (
                transaction is None
                or transaction.number != prepare_id
                or transaction.order_id != order_id
            ):
                raise ClickError(TRANSACTION_NOT_FOUND)
            if amount != transaction.amount_tiyin:
                raise ClickError(WRONG_AMOUNT)
            if transaction.state == TransactionState.PERFORMED:
                raise ClickError(ALREADY_PAID)
            if transaction.state != TransactionState.CREATED:
                raise ClickError(TRANSACTION_CANCELLED)
            if click_error < 0:
                # Click could not charge the customer: the transaction is over.
                await payments.cancel(session, transaction, reason=None, now=self._clock())
                cancelled = True
            else:
                payments.perform(session, transaction, now=self._clock())
        if cancelled:
            raise ClickError(TRANSACTION_CANCELLED)
        return transaction.number

    async def _existing(self, external_id: str) -> int | None:
        """A repeated prepare: the same prepare id, or why the transaction is over."""
        async with self._sessions() as session:
            transaction = await session.scalar(
                payments.by_external_id(PaymentProvider.CLICK, external_id)
            )
        if transaction is None:
            return None
        if transaction.state == TransactionState.PERFORMED:
            raise ClickError(ALREADY_PAID)
        if transaction.state != TransactionState.CREATED:
            raise ClickError(TRANSACTION_CANCELLED)
        return transaction.number

    def _verify(
        self,
        params: Mapping[str, str],
        fields: tuple[str, ...],
        *,
        action: int,
        with_prepare_id: bool,
    ) -> None:
        if any(not params.get(field) for field in fields):
            raise ClickError(BAD_REQUEST)
        expected = sign(params, self._secret_key, with_prepare_id=with_prepare_id)
        if not self._secret_key or not hmac.compare_digest(expected, params["sign_string"].lower()):
            raise ClickError(SIGN_FAILED)
        if self._service_id and params["service_id"] != self._service_id:
            raise ClickError(BAD_REQUEST, "Unknown service_id")
        if _int(params, "action") != action:
            raise ClickError(ACTION_NOT_FOUND)


def _echo(params: Mapping[str, str], id_field: str) -> dict[str, Any]:
    return {
        "click_trans_id": _int_or_none(params.get("click_trans_id")),
        "merchant_trans_id": params.get("merchant_trans_id"),
        id_field: None,
    }


def _with_error(answer: dict[str, Any], error: ClickError | None) -> dict[str, Any]:
    if error is not None:
        PAYMENT_ERRORS.labels(provider="click", code=str(error.code)).inc()
    answer["error"] = error.code if error is not None else SUCCESS
    answer["error_note"] = error.note if error is not None else NOTES[SUCCESS]
    return answer


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _int(params: Mapping[str, str], key: str) -> int:
    try:
        return int(params[key])
    except (KeyError, ValueError):
        raise ClickError(BAD_REQUEST) from None


def _amount(params: Mapping[str, str]) -> int:
    try:
        amount = Decimal(params["amount"])
    except (KeyError, InvalidOperation):
        raise ClickError(WRONG_AMOUNT) from None
    if not amount.is_finite() or amount <= 0:
        raise ClickError(WRONG_AMOUNT)
    return som_to_tiyin(amount)


def _order_id(params: Mapping[str, str]) -> UUID:
    try:
        return UUID(params["merchant_trans_id"])
    except (KeyError, ValueError):
        raise ClickError(ORDER_NOT_FOUND) from None
