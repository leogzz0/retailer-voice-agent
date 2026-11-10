"""ORM models for Nopalia's simulated back office.

Statuses are stored as plain strings (non-native enums) so adding a status later is a
code change, not a Postgres ALTER TYPE migration.
"""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _str_enum(enum_cls: type[enum.Enum]) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class OrderStatus(enum.StrEnum):
    RECEIVED = "received"
    PICKING = "picking"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class DeliveryStatus(enum.StrEnum):
    SCHEDULED = "scheduled"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    FAILED = "failed"


class DeliveryZone(enum.StrEnum):
    METRO = "metro"  # Monterrey metro area: order cutoff 18:00
    FORANEO = "foraneo"  # outside the metro area: order cutoff 14:00


class Customer(Base):
    """A tienda de abarrotes that buys from Nopalia."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    # What the shopkeeper reads from their invoice, e.g. "10234". Numeric so it is easy to say.
    customer_code: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    store_name: Mapped[str] = mapped_column(String(120))
    owner_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # E.164
    city: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(80))
    credit_limit_mxn: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    credit_used_mxn: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    zone: Mapped[DeliveryZone] = mapped_column(
        _str_enum(DeliveryZone), server_default=DeliveryZone.METRO.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    # Space-separated nicknames shopkeepers actually say ("chetos", "sopa de vasito"...).
    search_terms: Mapped[str] = mapped_column(String(400), default="")
    category: Mapped[str] = mapped_column(String(60))
    unit: Mapped[str] = mapped_column(String(60))  # e.g. "caja con 24 piezas"
    price_mxn: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    active: Mapped[bool] = mapped_column(default=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Short numeric folio printed on the remisión; what callers read out loud.
    # Seeded orders use explicit folios; new ones come from a sequence (no MAX()+1 races).
    folio: Mapped[int] = mapped_column(
        Integer, unique=True, index=True, server_default=text("nextval('order_folio_seq')")
    )
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[OrderStatus] = mapped_column(_str_enum(OrderStatus))
    channel: Mapped[str] = mapped_column(String(20), default="sales_rep")
    total_mxn: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    promised_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    customer: Mapped[Customer] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    delivery: Mapped["Delivery | None"] = relationship(back_populates="order", uselist=False)


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_mxn: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    route_code: Mapped[str] = mapped_column(String(20))
    driver_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[DeliveryStatus] = mapped_column(_str_enum(DeliveryStatus))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(200))

    order: Mapped[Order] = relationship(back_populates="delivery")


# --- M2: integration hardening ----------------------------------------------------------


class VerificationAttempt(Base):
    """Every caller-verification attempt; failures within a window lock the account."""

    __tablename__ = "verification_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(String(128))
    method: Mapped[str] = mapped_column(String(20))  # caller_id | phone_last4
    success: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IdempotencyKey(Base):
    """Stored responses for write tools: a replayed request returns the original result."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("key", "operation", name="uq_idempotency_key_operation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(128))
    operation: Mapped[str] = mapped_column(String(40))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int]
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IncidentKind(enum.StrEnum):
    NOT_DELIVERED = "not_delivered"
    INCOMPLETE = "incomplete"
    DAMAGED = "damaged"
    WRONG_ITEMS = "wrong_items"
    OTHER = "other"


class Incident(Base):
    """A delivery problem reported by a store; lands in the logistics queue."""

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_number: Mapped[str | None] = mapped_column(String(20), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    kind: Mapped[IncidentKind] = mapped_column(_str_enum(IncidentKind))
    description: Mapped[str] = mapped_column(String(500))
    conversation_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class HandoffReason(enum.StrEnum):
    CALLER_REQUEST = "caller_request"
    OUT_OF_SCOPE = "out_of_scope"
    NOT_UNDERSTOOD = "not_understood"
    CREDIT = "credit"
    COMPLAINT = "complaint"
    VERIFICATION_FAILED = "verification_failed"


class HandoffStatus(enum.StrEnum):
    PENDING = "pending"  # stored, not yet in the ticketing system
    SENT = "sent"
    FAILED = "failed"  # retries exhausted; `make retry-handoffs` picks it up


class HandoffRequest(Base):
    """Outbox row: written in the request transaction, delivered to ticketing afterwards.

    The caller is promised a callback as soon as this row commits, even if the ticketing
    system is down at that moment.
    """

    __tablename__ = "handoff_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str | None] = mapped_column(String(20), unique=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    reason: Mapped[HandoffReason] = mapped_column(_str_enum(HandoffReason))
    summary: Mapped[str] = mapped_column(String(1000))
    callback_phone: Mapped[str | None] = mapped_column(String(20))
    conversation_id: Mapped[str] = mapped_column(String(128))
    status: Mapped[HandoffStatus] = mapped_column(_str_enum(HandoffStatus), index=True)
    external_ticket_id: Mapped[str | None] = mapped_column(String(40))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Conversation(Base):
    """One row per ElevenLabs conversation, from the post-call webhook (dedup by id)."""

    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    agent_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str | None] = mapped_column(String(40))
    call_duration_secs: Mapped[int | None]
    transcript_summary: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
