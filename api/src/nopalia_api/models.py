"""ORM models for Nopalia's simulated back office.

Statuses are stored as plain strings (non-native enums) so adding a status later is a
code change, not a Postgres ALTER TYPE migration.
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
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
    folio: Mapped[int] = mapped_column(Integer, unique=True, index=True)
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
