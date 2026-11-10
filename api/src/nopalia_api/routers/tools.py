"""Endpoints the ElevenLabs agent calls as server tools.

Layers of protection, outermost first:
1. Every /v1 route requires the tool bearer token (the request comes from OUR agent).
2. Every /v1/customers/{code}/... route except lookup and verify requires a verification
   token bound to that store and that conversation (the CALLER proved they own the store).
3. Writes require an Idempotency-Key (retries and LLM double-calls create nothing twice).
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from nopalia_api import schemas, services, verification, writes
from nopalia_api.config import Settings, get_settings
from nopalia_api.db import get_engine, get_session
from nopalia_api.idempotency import run_idempotent
from nopalia_api.models import Customer, OrderStatus
from nopalia_api.security import require_tool_token
from nopalia_api.ticketing import TicketingClient, deliver_handoff, get_ticketing_client

router = APIRouter(prefix="/v1", tags=["agent-tools"], dependencies=[Depends(require_tool_token)])

DB = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
VerifiedCustomer = Annotated[Customer, Depends(verification.verified_customer)]
ConversationId = Annotated[str, Header(min_length=1, max_length=128)]
IdempotencyKey = Annotated[str, Header(min_length=8, max_length=128)]

_ERR: dict[str, object] = {"model": schemas.ErrorBody}
_ERRORS: dict[int | str, dict[str, object]] = {
    401: _ERR, 403: _ERR, 404: _ERR, 409: _ERR, 422: _ERR, 429: _ERR,
}  # fmt: skip


def _json(status: int, body: dict[str, object], replayed: bool) -> JSONResponse:
    headers = {"Idempotent-Replayed": "true"} if replayed else None
    return JSONResponse(status_code=status, content=body, headers=headers)


# --- identification & verification -------------------------------------------------------


@router.get("/customers/lookup", response_model=schemas.CustomerLookupOut, responses=_ERRORS)
def lookup_customer(
    db: DB,
    customer_code: Annotated[str | None, Query(max_length=20)] = None,
    phone: Annotated[str | None, Query(max_length=25)] = None,
) -> schemas.CustomerLookupOut:
    """Identify the store (name + city only, to confirm with the caller). Not verification."""
    return services.lookup_out(services.find_customer(db, phone=phone, customer_code=customer_code))


@router.post(
    "/customers/{customer_code}/verify", response_model=schemas.VerifyOut, responses=_ERRORS
)
def verify_customer(
    customer_code: str,
    body: schemas.VerifyIn,
    db: DB,
    settings: SettingsDep,
    x_conversation_id: ConversationId,
    x_caller_id: Annotated[str | None, Header(max_length=40)] = None,
) -> schemas.VerifyOut:
    """Verify the caller (caller ID or last 4 digits of the registered phone)."""
    customer = services.find_customer(db, phone=None, customer_code=customer_code)
    return verification.verify_caller(
        db,
        settings,
        customer,
        conversation_id=x_conversation_id,
        phone_last4=body.phone_last4,
        caller_id=x_caller_id,
    )


# --- reads (verified) --------------------------------------------------------------------


@router.get(
    "/customers/{customer_code}/orders", response_model=schemas.OrderList, responses=_ERRORS
)
def list_orders(
    db: DB,
    customer: VerifiedCustomer,
    status: OrderStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=10)] = 3,
) -> schemas.OrderList:
    """Most recent orders for the store, newest first."""
    return services.list_orders(db, customer, status=status, limit=limit)


@router.get(
    "/customers/{customer_code}/orders/{folio}",
    response_model=schemas.OrderDetail,
    responses=_ERRORS,
)
def get_order(db: DB, customer: VerifiedCustomer, folio: int) -> schemas.OrderDetail:
    """Status, items and delivery window for one order."""
    return services.get_order(db, customer, folio)


@router.get(
    "/customers/{customer_code}/usual-order", response_model=schemas.UsualOrder, responses=_ERRORS
)
def usual_order(db: DB, customer: VerifiedCustomer) -> schemas.UsualOrder:
    """The store's typical basket, used to offer '¿le repito su pedido de siempre?'."""
    return services.usual_order(db, customer)


@router.get("/products/search", response_model=schemas.ProductSearchResult)
def search_products(
    db: DB,
    q: Annotated[str, Query(min_length=2, max_length=80)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> schemas.ProductSearchResult:
    """Fuzzy product search tolerant to accents, typos and nicknames. Catalog is public."""
    return services.search_products(db, q, limit)


# --- writes (verified + idempotent) ------------------------------------------------------


@router.post(
    "/customers/{customer_code}/reorders",
    response_model=schemas.ReorderOut,
    status_code=201,
    responses=_ERRORS,
)
def create_reorder(
    body: schemas.ReorderIn,
    db: DB,
    customer: VerifiedCustomer,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Place an order for the store; delivery date follows the zone's cutoff."""
    status, out, replayed = run_idempotent(
        db,
        key=idempotency_key,
        operation="reorder",
        scope=customer.customer_code,
        payload=body,
        action=lambda: writes.create_reorder(db, customer.id, body),
    )
    return _json(status, out, replayed)


@router.post(
    "/customers/{customer_code}/incidents",
    response_model=schemas.IncidentOut,
    status_code=201,
    responses=_ERRORS,
)
def report_incident(
    body: schemas.IncidentIn,
    db: DB,
    customer: VerifiedCustomer,
    idempotency_key: IdempotencyKey,
    x_conversation_id: ConversationId,
) -> JSONResponse:
    """Report a delivery problem on one of the store's orders."""
    status, out, replayed = run_idempotent(
        db,
        key=idempotency_key,
        operation="incident",
        scope=customer.customer_code,
        payload=body,
        action=lambda: writes.create_incident(db, customer, body, x_conversation_id),
    )
    return _json(status, out, replayed)


def _deliver_in_background(reference: str, client: TicketingClient) -> None:
    with Session(get_engine()) as db:
        deliver_handoff(db, reference, client)


@router.post("/handoffs", response_model=schemas.HandoffOut, status_code=202, responses=_ERRORS)
def request_handoff(
    body: schemas.HandoffIn,
    db: DB,
    idempotency_key: IdempotencyKey,
    x_conversation_id: ConversationId,
    background: BackgroundTasks,
    ticketing: Annotated[TicketingClient, Depends(get_ticketing_client)],
) -> JSONResponse:
    """Hand the caller to a human. The callback is promised once the request is stored;
    delivery to the ticketing system happens after the response (outbox pattern)."""
    status, out, replayed = run_idempotent(
        db,
        key=idempotency_key,
        operation="handoff",
        scope=x_conversation_id,
        payload=body,
        action=lambda: writes.create_handoff(db, body, x_conversation_id),
    )
    background.add_task(_deliver_in_background, str(out["reference"]), ticketing)
    return _json(status, out, replayed)
