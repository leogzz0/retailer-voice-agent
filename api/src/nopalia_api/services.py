"""Read-side business queries. Routers stay thin; everything testable lives here."""

import re
from datetime import date

from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session, selectinload

from nopalia_api import schemas, speech
from nopalia_api.clock import today_local
from nopalia_api.config import get_settings
from nopalia_api.errors import ToolError
from nopalia_api.models import Customer, Order, OrderItem, OrderStatus, Product


def normalize_mx_phone(raw: str) -> str | None:
    """'81 1234 5678', '+52 1 81-1234-5678', '528112345678' -> '+528112345678'."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10:
        return None
    return f"+52{digits[-10:]}"


# --- customers ---------------------------------------------------------------------------


def find_customer(db: Session, *, phone: str | None, customer_code: str | None) -> Customer:
    if customer_code:
        code = re.sub(r"\D", "", customer_code)  # "diez mil 234" arrives as "10 234"
        customer = db.scalar(select(Customer).where(Customer.customer_code == code))
    elif phone:
        normalized = normalize_mx_phone(phone)
        customer = (
            db.scalar(select(Customer).where(Customer.phone == normalized)) if normalized else None
        )
    else:
        raise ToolError(
            422,
            "missing_identifier",
            "Necesito el número de cliente o el teléfono registrado para buscar la cuenta.",
        )
    if customer is None:
        raise ToolError(
            404,
            "customer_not_found",
            "No encontré una tienda con ese dato. Pide que lo repita dígito por dígito.",
        )
    return customer


def lookup_out(c: Customer) -> schemas.CustomerLookupOut:
    return schemas.CustomerLookupOut(
        customer_code=c.customer_code, store_name=c.store_name, city=c.city
    )


# --- orders ------------------------------------------------------------------------------


def _summary(o: Order, today: date) -> schemas.OrderSummary:
    return schemas.OrderSummary(
        folio=o.folio,
        status=o.status.value,
        status_es=speech.ORDER_STATUS_ES[o.status],
        promised_date=o.promised_date,
        promised_date_es=speech.date_es(o.promised_date, today),
        total_mxn=o.total_mxn,
        item_count=sum(i.quantity for i in o.items),
    )


def list_orders(
    db: Session, customer: Customer, *, status: OrderStatus | None, limit: int
) -> schemas.OrderList:
    stmt = (
        select(Order)
        .where(Order.customer_id == customer.id)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc(), Order.folio.desc())
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(Order.status == status)
    today = today_local()
    return schemas.OrderList(
        customer_code=customer.customer_code,
        orders=[_summary(o, today) for o in db.scalars(stmt)],
    )


def order_for_customer(db: Session, customer: Customer, folio: int) -> Order:
    # Scoped by customer on purpose: a caller can only hear about their own orders,
    # so guessing folios does not leak other stores' data.
    order = db.scalar(
        select(Order)
        .where(Order.folio == folio, Order.customer_id == customer.id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product),
            selectinload(Order.delivery),
        )
    )
    if order is None:
        raise ToolError(
            404,
            "order_not_found",
            "No encontré ese folio en las órdenes de esta tienda. "
            "Confirma el folio dígito por dígito o ofrece revisar sus pedidos recientes.",
        )
    return order


def get_order(db: Session, customer: Customer, folio: int) -> schemas.OrderDetail:
    order = order_for_customer(db, customer, folio)
    today = today_local()
    d = order.delivery
    delivery = (
        schemas.DeliveryOut(
            status=d.status.value,
            status_es=speech.DELIVERY_STATUS_ES[d.status],
            window_es=speech.window_es(
                d.window_start, d.window_end, get_settings().timezone, today
            ),
            driver_first_name=speech.first_name(d.driver_name),
            delivered_at=d.delivered_at,
            failure_reason=d.failure_reason,
        )
        if d
        else None
    )
    return schemas.OrderDetail(
        **_summary(order, today).model_dump(),
        items=[
            schemas.OrderItemOut(
                sku=i.product.sku, name=i.product.name, unit=i.product.unit, quantity=i.quantity
            )
            for i in order.items
        ],
        delivery=delivery,
    )


def usual_order(
    db: Session, customer: Customer, *, lookback_orders: int = 5, min_appearances: int = 2
) -> schemas.UsualOrder:
    """Products that show up in at least `min_appearances` of the last N non-cancelled orders."""
    recent_ids = (
        select(Order.id)
        .where(Order.customer_id == customer.id, Order.status != OrderStatus.CANCELLED)
        .order_by(Order.created_at.desc())
        .limit(lookback_orders)
        .subquery()
    )
    times = func.count(func.distinct(OrderItem.order_id)).label("times")
    typical = func.round(func.avg(OrderItem.quantity)).label("typical")
    rows = db.execute(
        select(Product, times, typical)
        .join(OrderItem, OrderItem.product_id == Product.id)
        .where(OrderItem.order_id.in_(select(recent_ids.c.id)), Product.active.is_(True))
        .group_by(Product.id)
        .having(times >= min_appearances)
        .order_by(times.desc(), Product.name)
    ).all()
    based_on = db.scalar(select(func.count()).select_from(recent_ids)) or 0
    return schemas.UsualOrder(
        customer_code=customer.customer_code,
        based_on_orders=based_on,
        items=[
            schemas.UsualOrderItem(
                sku=p.sku,
                name=p.name,
                unit=p.unit,
                typical_quantity=int(t_qty),
                times_ordered=int(t),
            )
            for p, t, t_qty in rows
        ],
    )


# --- products ----------------------------------------------------------------------------


def search_products(db: Session, query: str, limit: int = 5) -> schemas.ProductSearchResult:
    """Fuzzy, accent-insensitive search over names and shopkeeper nicknames (pg_trgm).

    Speech-to-text gives us "chetos", "sopita de vaso", "galletas maria"; exact matching
    would fail most real calls. Threshold and ambiguity margin are settings because they
    must be re-tuned against the real catalog, not this 26-SKU sample.
    """
    settings = get_settings()
    q = func.unaccent(func.lower(query))
    name_score = func.word_similarity(q, func.unaccent(func.lower(Product.name)))
    terms_score = func.word_similarity(q, func.unaccent(func.lower(Product.search_terms)))
    score = cast(func.greatest(name_score, terms_score), Float).label("score")
    rows = db.execute(
        select(Product, score)
        .where(Product.active.is_(True), score >= settings.product_match_threshold)
        .order_by(score.desc(), Product.name)
        .limit(limit)
    ).all()
    matches = [
        schemas.ProductMatch(
            sku=p.sku, name=p.name, unit=p.unit, price_mxn=p.price_mxn, score=round(s, 2)
        )
        for p, s in rows
    ]
    ambiguous = len(rows) >= 2 and (rows[0][1] - rows[1][1]) < settings.product_ambiguity_margin
    return schemas.ProductSearchResult(query=query, matches=matches, ambiguous=ambiguous)
