"""Request/response contracts for agent tools.

Design rules (see docs/adr/0002-tool-api-contract.md):
- Small payloads: every field costs LLM tokens and latency.
- Each spoken value has a pre-rendered `*_es` field next to its machine value.
- No PII beyond what the agent needs to say (first names only, no phone numbers back).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field

from nopalia_api.models import HandoffReason, IncidentKind

# --- errors ------------------------------------------------------------------------------


class ErrorBody(BaseModel):
    """Errors are written so the agent can relay them; `code` is for our logs and tests."""

    code: str
    message_es: str
    fields: list[str] | None = None


# --- customers & verification ------------------------------------------------------------


class CustomerLookupOut(BaseModel):
    """Identification only: enough to ask '¿hablo de Abarrotes Doña Lupe?'. Nothing sensitive."""

    customer_code: str
    store_name: str
    city: str


class VerifyIn(BaseModel):
    phone_last4: Annotated[str | None, Field(pattern=r"^\d{4}$")] = None


class VerifyOut(BaseModel):
    verified: bool
    # Echoed so the agent can pin it in a dynamic variable and reuse it for every
    # store-scoped URL: the LLM never chooses the store after verification.
    customer_code: str
    verification_token: str
    expires_in_s: int
    store_name: str
    owner_first_name: str
    credit_available_mxn: Decimal


# --- orders ------------------------------------------------------------------------------


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


# --- products ----------------------------------------------------------------------------


class ProductMatch(BaseModel):
    sku: str
    name: str
    unit: str
    price_mxn: Decimal
    score: float


class ProductSearchResult(BaseModel):
    query: str
    matches: list[ProductMatch]
    # True when the top two matches are too close to pick: the agent should ask.
    ambiguous: bool


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


# --- writes ------------------------------------------------------------------------------


class ReorderLine(BaseModel):
    sku: Annotated[str, Field(min_length=3, max_length=20)]
    quantity: Annotated[int, Field(ge=1, le=50)]


class ReorderIn(BaseModel):
    items: Annotated[list[ReorderLine], Field(min_length=1, max_length=20)]


class ReorderOut(BaseModel):
    folio: int
    total_mxn: Decimal
    promised_date: date
    promised_date_es: str
    after_cutoff: bool
    cutoff_es: str
    credit_available_mxn: Decimal


class IncidentIn(BaseModel):
    folio: int
    kind: IncidentKind
    description: Annotated[str, Field(min_length=5, max_length=500)]


class IncidentOut(BaseModel):
    ticket_number: str
    folio: int
    kind: IncidentKind
    message_es: str


class HandoffIn(BaseModel):
    reason: HandoffReason
    summary: Annotated[str, Field(min_length=5, max_length=1000)]
    customer_code: Annotated[str | None, Field(max_length=20)] = None
    callback_phone: Annotated[str | None, Field(max_length=25)] = None


class HandoffOut(BaseModel):
    reference: str
    message_es: str
