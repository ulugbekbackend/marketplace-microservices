"""Payme Merchant API (JSON-RPC 2.0): Payme calls us, we answer with HTTP 200 and either
``result`` or ``error``.

    Check -> Create -> Perform, plus Cancel, CheckTransaction and GetStatement.

States: 1 created, 2 performed, -1 cancelled, -2 cancelled after perform. A created
transaction lives 12 hours; Perform or Create on an older one cancels it (reason 4) and
answers -31008. Every call is idempotent: a repeated Create / Perform / Cancel returns the
stored result and never writes money twice.
"""

import base64
import binascii
import hmac
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Transaction, TransactionState
from app.services import payments
from app.services.orders import OrderClient, OrderUnavailableError, Payable
from contracts.enums import OrderStatus, PaymentProvider

logger = logging.getLogger(__name__)

TRANSACTION_TIMEOUT = timedelta(hours=12)
LOGIN = "Paycom"

# Cancel reasons (Payme numbering).
REASON_TIMEOUT = 4

# Error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INSUFFICIENT_PRIVILEGE = -32504
SYSTEM_ERROR = -32400
WRONG_AMOUNT = -31001
TRANSACTION_NOT_FOUND = -31003
CANNOT_CANCEL = -31007
CANNOT_PERFORM = -31008
ORDER_NOT_FOUND = -31050
ORDER_NOT_PAYABLE = -31051
ORDER_HAS_ACTIVE_TRANSACTION = -31052

MESSAGES: dict[int, tuple[str, str, str]] = {
    PARSE_ERROR: ("Ошибка разбора JSON", "JSON xato", "Parse error"),
    INVALID_REQUEST: ("Неверный запрос", "Noto'g'ri so'rov", "Invalid request"),
    METHOD_NOT_FOUND: ("Метод не найден", "Metod topilmadi", "Method not found"),
    INSUFFICIENT_PRIVILEGE: ("Недостаточно привилегий", "Ruxsat yo'q", "Insufficient privilege"),
    SYSTEM_ERROR: ("Системная ошибка", "Tizim xatosi", "System error"),
    WRONG_AMOUNT: ("Неверная сумма", "Noto'g'ri summa", "Wrong amount"),
    TRANSACTION_NOT_FOUND: ("Транзакция не найдена", "Tranzaksiya topilmadi", "Not found"),
    CANNOT_CANCEL: ("Невозможно отменить", "Bekor qilib bo'lmaydi", "Cannot cancel"),
    CANNOT_PERFORM: ("Невозможно выполнить", "Bajarib bo'lmaydi", "Cannot perform"),
    ORDER_NOT_FOUND: ("Заказ не найден", "Buyurtma topilmadi", "Order not found"),
    ORDER_NOT_PAYABLE: ("Заказ нельзя оплатить", "Buyurtmani to'lab bo'lmaydi", "Not payable"),
    ORDER_HAS_ACTIVE_TRANSACTION: (
        "Заказ ожидает оплаты",
        "Buyurtma to'lovi kutilmoqda",
        "Order has a pending transaction",
    ),
}

#: Account errors name the field Payme should highlight.
ACCOUNT_ERRORS = {ORDER_NOT_FOUND, ORDER_NOT_PAYABLE, ORDER_HAS_ACTIVE_TRANSACTION}

#: Orders whose payment can no longer be reversed through Payme.
NOT_CANCELLABLE = {OrderStatus.COMPLETED.value}


class PaymeError(Exception):
    def __init__(self, code: int, data: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.data = data if data is not None else ("order_id" if code in ACCOUNT_ERRORS else None)

    def body(self) -> dict[str, Any]:
        ru, uz, en = MESSAGES[self.code]
        error: dict[str, Any] = {"code": self.code, "message": {"ru": ru, "uz": uz, "en": en}}
        if self.data is not None:
            error["data"] = self.data
        return error


def to_ms(value: datetime | None) -> int:
    return int(value.timestamp() * 1000) if value is not None else 0


def from_ms(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, UTC)


def basic_auth(key: str) -> str:
    return "Basic " + base64.b64encode(f"{LOGIN}:{key}".encode()).decode()


class PaymeMerchant:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        orders: OrderClient,
        *,
        key: str,
        clock: Callable[[], datetime] = payments.utcnow,
    ) -> None:
        self._sessions = sessions
        self._orders = orders
        self._key = key
        self._clock = clock
        self._methods = {
            "CheckPerformTransaction": self.check_perform_transaction,
            "CreateTransaction": self.create_transaction,
            "PerformTransaction": self.perform_transaction,
            "CancelTransaction": self.cancel_transaction,
            "CheckTransaction": self.check_transaction,
            "GetStatement": self.get_statement,
        }

    # --- transport ----------------------------------------------------------------------

    def authorized(self, header: str | None) -> bool:
        if not self._key or not header or not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:], validate=True).decode()
        except (binascii.Error, UnicodeDecodeError):
            return False
        login, _, password = decoded.partition(":")
        return hmac.compare_digest(login, LOGIN) and hmac.compare_digest(password, self._key)

    async def handle(self, body: bytes, authorization: str | None) -> dict[str, Any]:
        """One JSON-RPC call in, one JSON-RPC answer out."""
        request_id: Any = None
        try:
            try:
                request = json.loads(body)
            except ValueError as exc:
                raise PaymeError(PARSE_ERROR) from exc
            if not isinstance(request, dict):
                raise PaymeError(INVALID_REQUEST)
            request_id = request.get("id")
            if not self.authorized(authorization):
                raise PaymeError(INSUFFICIENT_PRIVILEGE)
            method = self._methods.get(str(request.get("method")))
            if method is None:
                raise PaymeError(METHOD_NOT_FOUND, data=str(request.get("method")))
            params = request.get("params")
            if not isinstance(params, dict):
                raise PaymeError(INVALID_REQUEST)
            result = await method(params)
        except PaymeError as error:
            return {"jsonrpc": "2.0", "id": request_id, "error": error.body()}
        except OrderUnavailableError:
            logger.warning("order service unavailable for payme", exc_info=True)
            return {"jsonrpc": "2.0", "id": request_id, "error": PaymeError(SYSTEM_ERROR).body()}
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    # --- methods ------------------------------------------------------------------------

    async def check_perform_transaction(self, params: dict[str, Any]) -> dict[str, Any]:
        await self._payable_order(_order_id(params), _amount(params))
        return {"allow": True}

    async def create_transaction(self, params: dict[str, Any]) -> dict[str, Any]:
        external_id = _transaction_id(params)
        existing = await self._create_existing(external_id)
        if existing is not None:
            return existing
        order_id = _order_id(params)
        amount = _amount(params)
        await self._payable_order(order_id, amount)
        provider_time = from_ms(_int(params, "time"))
        try:
            async with self._sessions.begin() as session:
                if await payments.active_for_order(session, order_id) is not None:
                    raise PaymeError(ORDER_HAS_ACTIVE_TRANSACTION)
                transaction = payments.create(
                    session,
                    order_id=order_id,
                    provider=PaymentProvider.PAYME,
                    external_id=external_id,
                    amount_tiyin=amount,
                    now=self._clock(),
                    provider_time=provider_time,
                )
        except IntegrityError:
            # A concurrent Create won: the same id returns its result, another id is refused.
            existing = await self._create_existing(external_id)
            if existing is not None:
                return existing
            raise PaymeError(ORDER_HAS_ACTIVE_TRANSACTION) from None
        return _created(transaction)

    async def perform_transaction(self, params: dict[str, Any]) -> dict[str, Any]:
        external_id = _transaction_id(params)
        timed_out = False
        async with self._sessions.begin() as session:
            transaction = await self._lock(session, external_id)
            if transaction.state == TransactionState.CREATED:
                now = self._clock()
                if self._timed_out(transaction, now):
                    await payments.cancel(session, transaction, reason=REASON_TIMEOUT, now=now)
                    timed_out = True
                else:
                    payments.perform(session, transaction, now=now)
            elif transaction.state != TransactionState.PERFORMED:
                raise PaymeError(CANNOT_PERFORM)
        if timed_out:
            raise PaymeError(CANNOT_PERFORM)
        return {
            "transaction": str(transaction.id),
            "perform_time": to_ms(transaction.perform_time),
            "state": transaction.state,
        }

    async def cancel_transaction(self, params: dict[str, Any]) -> dict[str, Any]:
        external_id = _transaction_id(params)
        reason = _int(params, "reason")
        async with self._sessions() as session:
            current = await session.scalar(
                payments.by_external_id(PaymentProvider.PAYME, external_id)
            )
        if current is None:
            raise PaymeError(TRANSACTION_NOT_FOUND)
        if current.state == TransactionState.PERFORMED:
            order = await self._orders.payable(current.order_id)
            if order is not None and order.status in NOT_CANCELLABLE:
                raise PaymeError(CANNOT_CANCEL)
        async with self._sessions.begin() as session:
            transaction = await self._lock(session, external_id)
            await payments.cancel(session, transaction, reason=reason, now=self._clock())
        return {
            "transaction": str(transaction.id),
            "cancel_time": to_ms(transaction.cancel_time),
            "state": transaction.state,
        }

    async def check_transaction(self, params: dict[str, Any]) -> dict[str, Any]:
        external_id = _transaction_id(params)
        async with self._sessions() as session:
            transaction = await session.scalar(
                payments.by_external_id(PaymentProvider.PAYME, external_id)
            )
        if transaction is None:
            raise PaymeError(TRANSACTION_NOT_FOUND)
        return {
            "create_time": to_ms(transaction.create_time),
            "perform_time": to_ms(transaction.perform_time),
            "cancel_time": to_ms(transaction.cancel_time),
            "transaction": str(transaction.id),
            "state": transaction.state,
            "reason": transaction.reason,
        }

    async def get_statement(self, params: dict[str, Any]) -> dict[str, Any]:
        start, end = from_ms(_int(params, "from")), from_ms(_int(params, "to"))
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(Transaction)
                    .where(
                        Transaction.provider == PaymentProvider.PAYME.value,
                        Transaction.provider_time >= start,
                        Transaction.provider_time <= end,
                    )
                    .order_by(Transaction.provider_time)
                )
            ).all()
        return {
            "transactions": [
                {
                    "id": row.external_id,
                    "time": to_ms(row.provider_time),
                    "amount": row.amount_tiyin,
                    "account": {"order_id": str(row.order_id)},
                    "create_time": to_ms(row.create_time),
                    "perform_time": to_ms(row.perform_time),
                    "cancel_time": to_ms(row.cancel_time),
                    "transaction": str(row.id),
                    "state": row.state,
                    "reason": row.reason,
                    "receivers": None,
                }
                for row in rows
            ]
        }

    # --- helpers ------------------------------------------------------------------------

    async def _payable_order(self, order_id: UUID, amount: int) -> Payable:
        order = await self._orders.payable(order_id)
        if order is None:
            raise PaymeError(ORDER_NOT_FOUND)
        if amount != order.amount_tiyin:
            raise PaymeError(WRONG_AMOUNT)
        if not order.payable:
            raise PaymeError(ORDER_NOT_PAYABLE)
        return order

    async def _create_existing(self, external_id: str) -> dict[str, Any] | None:
        """Create with a known id: its stored result, or the reason it cannot be reused."""
        timed_out = False
        async with self._sessions.begin() as session:
            transaction = await payments.lock(session, PaymentProvider.PAYME, external_id)
            if transaction is None:
                return None
            if transaction.state != TransactionState.CREATED:
                raise PaymeError(CANNOT_PERFORM)
            now = self._clock()
            if self._timed_out(transaction, now):
                await payments.cancel(session, transaction, reason=REASON_TIMEOUT, now=now)
                timed_out = True
        if timed_out:
            raise PaymeError(CANNOT_PERFORM)
        return _created(transaction)

    async def _lock(self, session: AsyncSession, external_id: str) -> Transaction:
        transaction = await payments.lock(session, PaymentProvider.PAYME, external_id)
        if transaction is None:
            raise PaymeError(TRANSACTION_NOT_FOUND)
        return transaction

    @staticmethod
    def _timed_out(transaction: Transaction, now: datetime) -> bool:
        return now - transaction.create_time > TRANSACTION_TIMEOUT


def _created(transaction: Transaction) -> dict[str, Any]:
    return {
        "create_time": to_ms(transaction.create_time),
        "transaction": str(transaction.id),
        "state": transaction.state,
    }


def _int(params: dict[str, Any], key: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise PaymeError(INVALID_REQUEST, data=key)
    return value


def _amount(params: dict[str, Any]) -> int:
    value = params.get("amount")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PaymeError(WRONG_AMOUNT)
    return value


def _transaction_id(params: dict[str, Any]) -> str:
    value = params.get("id")
    if not isinstance(value, str) or not value or len(value) > 64:
        raise PaymeError(INVALID_REQUEST, data="id")
    return value


def _order_id(params: dict[str, Any]) -> UUID:
    account = params.get("account")
    raw = account.get("order_id") if isinstance(account, dict) else None
    try:
        return UUID(str(raw))
    except ValueError:
        raise PaymeError(ORDER_NOT_FOUND) from None
