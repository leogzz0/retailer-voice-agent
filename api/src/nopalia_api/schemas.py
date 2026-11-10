"""Response contracts for agent tools.

Design rules (see docs/adr/0002-tool-api-contract.md):
- Small payloads: every field costs LLM tokens and latency.
- Each spoken value has a pre-rendered `*_es` field next to its machine value.
- No PII beyond what the agent needs to say (first names only, no phone numbers back).
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class CustomerOut(BaseModel):
    customer_code: str
    store_name: str
    owner_first_name: str
    city: str
    credit_available_mxn: Decimal


class OrderSummary(BaseModel):
    folio: int
    status: str
    status_es: str
    promised_date: date
    promised_date_es: str
    total_mxn: Decimal
    item_count: int


class OrderItemOut(BaseModel):
    sku: str
    name: str
    unit: str
    quantity: int


class DeliveryOut(BaseModel):
    status: str
    status_es: str
    window_es: str
    driver_first_name: str
    delivered_at: datetime | None
    failure_reason: str | None


class OrderDetail(OrderSummary):
    items: list[OrderItemOut]
    delivery: DeliveryOut | None


class OrderList(BaseModel):
    customer_code: str
    orders: list[OrderSummary]


class ProductMatch(BaseModel):
    sku: str
    name: str
    unit: str
    price_mxn: Decimal
    score: float


class ProductSearchResult(BaseModel):
    query: str
    matches: list[ProductMatch]


class UsualOrderItem(BaseModel):
    sku: str
    name: str
    unit: str
    typical_quantity: int
    times_ordered: int


class UsualOrder(BaseModel):
    customer_code: str
    based_on_orders: int
    items: list[UsualOrderItem]


class ErrorBody(BaseModel):
    """Errors are written so the agent can relay them; `code` is for our logs and tests."""

    code: str
    message_es: str
