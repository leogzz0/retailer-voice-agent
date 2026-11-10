"""Spanish (es-MX) formatting for values the voice agent will read aloud.

Why this lives in the API and not in the LLM: dates, weekdays and time windows are where
LLMs most often slip ("el jueves 13" when the 13th is a Friday). We hand the agent a
pre-rendered phrase and keep the ISO value next to it for anything that needs to compute.
Deliberately locale-independent (no setlocale) so it behaves the same in every container.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from nopalia_api.models import DeliveryStatus, OrderStatus

_WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]  # fmt: skip

ORDER_STATUS_ES: dict[OrderStatus, str] = {
    OrderStatus.RECEIVED: "recibido",
    OrderStatus.PICKING: "en preparación en almacén",
    OrderStatus.OUT_FOR_DELIVERY: "en ruta de entrega",
    OrderStatus.DELIVERED: "entregado",
    OrderStatus.CANCELLED: "cancelado",
}

DELIVERY_STATUS_ES: dict[DeliveryStatus, str] = {
    DeliveryStatus.SCHEDULED: "programada",
    DeliveryStatus.IN_TRANSIT: "en camino",
    DeliveryStatus.DELIVERED: "entregada",
    DeliveryStatus.FAILED: "no se pudo entregar",
}


def date_es(d: date, today: date | None = None) -> str:
    """'hoy, lunes 9 de noviembre' / 'mañana, ...' / 'jueves 12 de noviembre'."""
    base = f"{_WEEKDAYS[d.weekday()]} {d.day} de {_MONTHS[d.month - 1]}"
    if today is not None:
        delta = (d - today).days
        prefix = {0: "hoy", 1: "mañana", -1: "ayer"}.get(delta)
        if prefix:
            return f"{prefix}, {base}"
    return base


def time_es(dt: datetime) -> str:
    return f"{dt.hour}:{dt.minute:02d}"


def window_es(start: datetime, end: datetime, tz: str, today: date | None = None) -> str:
    """'mañana, jueves 12 de noviembre, entre 9:00 y 13:00' in the business timezone."""
    zone = ZoneInfo(tz)
    s, e = start.astimezone(zone), end.astimezone(zone)
    return f"{date_es(s.date(), today)}, entre {time_es(s)} y {time_es(e)}"


def first_name(full_name: str) -> str:
    """Only the first name is ever exposed to the agent (data minimization)."""
    return full_name.split()[0] if full_name.strip() else ""
