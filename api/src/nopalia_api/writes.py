"""Write-side business rules: reorders, delivery incidents, human handoffs.

Each function flushes but does not commit; `run_idempotent` owns the transaction.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from nopalia_api import schemas, services, speech
from nopalia_api.clock import now_local
from nopalia_api.errors import ToolError
from nopalia_api.models import (
    Customer,
    DeliveryZone,
    HandoffRequest,
    HandoffStatus,
    Incident,
    Order,
    OrderItem,
    OrderStatus,
    Product,
)

CUTOFF: dict[DeliveryZone, time] = {
    DeliveryZone.METRO: time(18, 0),
    DeliveryZone.FORANEO: time(14, 0),
}
SUNDAY = 6


def next_delivery_date(now: datetime, zone: DeliveryZone) -> tuple[date, bool]:
    """Next-day delivery if ordered before the zone's cutoff, else the day after.
    No deliveries on Sundays. (Holidays: out of scope for the pilot, see runbook.)
    Returns (date, after_cutoff)."""
    after_cutoff = now.time() >= CUTOFF[zone]
    d = now.date() + timedelta(days=2 if after_cutoff else 1)
    while d.weekday() == SUNDAY:
        d += timedelta(days=1)
    return d, after_cutoff


# --- reorder -----------------------------------------------------------------------------


def create_reorder(
    db: Session, customer_id: int, payload: schemas.ReorderIn
) -> tuple[int, schemas.ReorderOut]:
    # Lock the store row: two concurrent reorders must not both pass the credit check.
    customer = db.scalar(select(Customer).where(Customer.id == customer_id).with_for_update())
    assert customer is not None

    quantities: dict[str, int] = {}
    for line in payload.items:  # "two boxes ... and two more" -> one line of 4
        sku = line.sku.strip().upper()
        quantities[sku] = quantities.get(sku, 0) + line.quantity

    products = {
        p.sku: p
        for p in db.scalars(
            select(Product).where(Product.sku.in_(quantities), Product.active.is_(True))
        )
    }
    unknown = sorted(set(quantities) - set(products))
    if unknown:
        raise ToolError(
            422,
            "unknown_sku",
            "Algunos productos no se encontraron. Búscalos de nuevo por nombre antes de pedir.",
            fields=unknown,
        )

    total = sum((products[s].price_mxn * q for s, q in quantities.items()), Decimal("0"))
    available = customer.credit_limit_mxn - customer.credit_used_mxn
    if total > available:
        raise ToolError(
            422,
            "credit_limit_exceeded",
            f"El pedido suma {total:,.2f} pesos y el crédito disponible es "
            f"{max(available, Decimal('0')):,.2f} pesos. Ofrece reducir cantidades "
            "o transferir con el área de crédito.",
        )

    now = now_local()
    promised, after_cutoff = next_delivery_date(now, customer.zone)
    order = Order(
        customer_id=customer.id,
        status=OrderStatus.RECEIVED,
        channel="voice_agent",
        total_mxn=total,
        promised_date=promised,
        created_at=now,
        items=[
            OrderItem(product_id=products[s].id, quantity=q, unit_price_mxn=products[s].price_mxn)
            for s, q in quantities.items()
        ],
    )
    db.add(order)
    customer.credit_used_mxn += total
    db.flush()  # assigns folio from the sequence

    cutoff = CUTOFF[customer.zone]
    return 201, schemas.ReorderOut(
        folio=order.folio,
        total_mxn=total,
        promised_date=promised,
        promised_date_es=speech.date_es(promised, now.date()),
        after_cutoff=after_cutoff,
        cutoff_es=f"La hora de corte para su zona es a las {cutoff.hour}:00.",
        credit_available_mxn=customer.credit_limit_mxn - customer.credit_used_mxn,
    )


# --- incidents ---------------------------------------------------------------------------


def create_incident(
    db: Session, customer: Customer, payload: schemas.IncidentIn, conversation_id: str
) -> tuple[int, schemas.IncidentOut]:
    order = services.order_for_customer(db, customer, payload.folio)
    if order.status is OrderStatus.CANCELLED:
        raise ToolError(
            422,
            "order_cancelled",
            "Ese pedido está cancelado, no se puede reportar un problema de entrega.",
        )
    incident = Incident(
        customer_id=customer.id,
        order_id=order.id,
        kind=payload.kind,
        description=payload.description.strip(),
        conversation_id=conversation_id,
        created_at=now_local(),
    )
    db.add(incident)
    db.flush()
    incident.ticket_number = f"INC-{incident.id:06d}"
    return 201, schemas.IncidentOut(
        ticket_number=incident.ticket_number,
        folio=order.folio,
        kind=payload.kind,
        message_es="Logística revisará el reporte en un máximo de 24 horas hábiles.",
    )


# --- handoffs ----------------------------------------------------------------------------

HANDOFF_PROMISE_ES = (
    "Un asesor le devolverá la llamada en menos de 30 minutos, de lunes a sábado de 8:00 a 18:00."
)


def create_handoff(
    db: Session, payload: schemas.HandoffIn, conversation_id: str
) -> tuple[int, schemas.HandoffOut]:
    """Anyone may ask for a human, verified or not, so no verification dependency here.
    Unverified callers still get a callback; the advisor verifies them on the phone."""
    customer: Customer | None = None
    if payload.customer_code:
        try:
            customer = services.find_customer(db, phone=None, customer_code=payload.customer_code)
        except ToolError:
            customer = None  # don't block a handoff on a misheard code
    phone = services.normalize_mx_phone(payload.callback_phone or "")
    if phone is None and customer is not None:
        phone = customer.phone  # stored for the advisor, never returned to the agent

    now = now_local()
    handoff = HandoffRequest(
        customer_id=customer.id if customer else None,
        reason=payload.reason,
        summary=payload.summary.strip(),
        callback_phone=phone,
        conversation_id=conversation_id,
        status=HandoffStatus.PENDING,
        attempts=0,
        created_at=now,
        updated_at=now,
    )
    db.add(handoff)
    db.flush()
    handoff.reference = f"H-{handoff.id:06d}"
    return 202, schemas.HandoffOut(reference=handoff.reference, message_es=HANDOFF_PROMISE_ES)
