"""Enumerations shared by every service. Values are stored in databases and events."""

from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"
    SELLER = "seller"
    ADMIN = "admin"


class ProductStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    COMMITTED = "committed"
    RELEASED = "released"


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    RESERVED = "RESERVED"
    PAID = "PAID"
    FULFILLING = "FULFILLING"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class SubOrderStatus(StrEnum):
    NEW = "NEW"
    ACCEPTED = "ACCEPTED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED_BY_SELLER = "CANCELLED_BY_SELLER"


class PaymentProvider(StrEnum):
    PAYME = "payme"
    CLICK = "click"
    MOCK = "mock"


class EventType(StrEnum):
    ORDER_CREATED = "order.created"
    STOCK_RESERVED = "stock.reserved"
    STOCK_FAILED = "stock.failed"
    PAYMENT_PAID = "payment.paid"
    PAYMENT_REFUNDED = "payment.refunded"
    ORDER_PAID = "order.paid"
    ORDER_EXPIRED = "order.expired"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_REFUND_REQUESTED = "order.refund_requested"
    SUB_ORDER_STATUS_CHANGED = "sub_order.status_changed"
    PRODUCT_UPDATED = "product.updated"
    PRODUCT_DELETED = "product.deleted"
    SELLER_APPROVED = "seller.approved"
