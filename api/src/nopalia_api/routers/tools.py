"""Endpoints the ElevenLabs agent calls as server tools.

Every route that touches store data is nested under /customers/{customer_code}: the agent
must identify the store first, and the API enforces that scoping (not the prompt).
Auth, idempotent writes and request logging arrive in milestone 2.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from nopalia_api import schemas, services
from nopalia_api.db import get_session
from nopalia_api.models import Customer, OrderStatus

router = APIRouter(prefix="/v1", tags=["agent-tools"])

DB = Annotated[Session, Depends(get_session)]
_ERRORS: dict[int | str, dict[str, object]] = {
    404: {"model": schemas.ErrorBody},
    422: {"model": schemas.ErrorBody},
}


def _customer(customer_code: Annotated[str, Path(max_length=20)], db: DB) -> Customer:
    return services.find_customer(db, phone=None, customer_code=customer_code)


CurrentCustomer = Annotated[Customer, Depends(_customer)]


@router.get("/customers/lookup", response_model=schemas.CustomerOut, responses=_ERRORS)
def lookup_customer(
    db: DB,
    customer_code: Annotated[str | None, Query(max_length=20)] = None,
    phone: Annotated[str | None, Query(max_length=25)] = None,
) -> schemas.CustomerOut:
    """Identify the calling store by customer code (from the invoice) or registered phone."""
    return services.customer_out(
        services.find_customer(db, phone=phone, customer_code=customer_code)
    )


@router.get(
    "/customers/{customer_code}/orders", response_model=schemas.OrderList, responses=_ERRORS
)
def list_orders(
    db: DB,
    customer: CurrentCustomer,
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
def get_order(db: DB, customer: CurrentCustomer, folio: int) -> schemas.OrderDetail:
    """Status, items and delivery window for one order."""
    return services.get_order(db, customer, folio)


@router.get(
    "/customers/{customer_code}/usual-order", response_model=schemas.UsualOrder, responses=_ERRORS
)
def usual_order(db: DB, customer: CurrentCustomer) -> schemas.UsualOrder:
    """The store's typical basket, used to offer '¿le repito su pedido de siempre?'."""
    return services.usual_order(db, customer)


@router.get("/products/search", response_model=schemas.ProductSearchResult)
def search_products(
    db: DB,
    q: Annotated[str, Query(min_length=2, max_length=80)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> schemas.ProductSearchResult:
    """Fuzzy product search tolerant to accents, typos and nicknames."""
    return services.search_products(db, q, limit)
