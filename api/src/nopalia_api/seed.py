"""Deterministic, fictional seed data for local dev and demos.

Usage:  python -m nopalia_api.seed

- Everything is invented: store names, people, phones (81-5550-xxxx), products, brands.
- Dates are generated relative to *today* in America/Monterrey so the demo always has an
  order "en ruta" today, one with a failed delivery yesterday, etc.
- Wipes and reloads all tables. Refuses to run unless NOPALIA_ENVIRONMENT is local/test.
"""

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from nopalia_api.config import get_settings
from nopalia_api.db import get_engine
from nopalia_api.models import (
    Customer,
    Delivery,
    DeliveryStatus,
    Order,
    OrderItem,
    OrderStatus,
    Product,
)

# (sku, name, search_terms, category, unit, price)
PRODUCTS: list[tuple[str, str, str, str, str, str]] = [
    ("BOT-001", "Papas fritas Crujis sal de mar 45 g", "papitas papas de bolsa crujis", "botanas", "caja con 30 bolsas", "312.00"),
    ("BOT-002", "Botana de maíz Crujis sabor queso 52 g", "churritos de queso quesitos crujis queso", "botanas", "caja con 30 bolsas", "298.50"),
    ("BOT-003", "Cacahuates japoneses Crujis 100 g", "japoneses cacahuate garapiñado", "botanas", "caja con 20 bolsas", "276.00"),
    ("BOT-004", "Chicharrón de harina picante Crujis 60 g", "duritos chicharroncitos de harina", "botanas", "caja con 25 bolsas", "215.00"),
    ("BEB-001", "Refresco Nopalia Cola 600 ml", "refresco negro cola refresco de cola", "bebidas", "paquete con 12 botellas", "168.00"),
    ("BEB-002", "Refresco Nopalia sabor toronja 600 ml", "refresco de toronja", "bebidas", "paquete con 12 botellas", "160.00"),
    ("BEB-003", "Agua purificada Nopalia 1 L", "agua natural botella de agua garrafita", "bebidas", "paquete con 12 botellas", "96.00"),
    ("BEB-004", "Jugo de mango Nopalia 250 ml", "juguito de mango jugo de cajita", "bebidas", "caja con 24 piezas", "204.00"),
    ("ABA-001", "Sopa instantánea Nopalia sabor pollo en vaso 64 g", "sopa de vasito sopita instantanea sopa de pollo", "abarrotes", "caja con 12 vasos", "138.00"),
    ("ABA-002", "Frijoles bayos refritos Nopalia lata 430 g", "frijolitos refritos frijol de lata", "abarrotes", "caja con 12 latas", "252.00"),
    ("ABA-003", "Atún en agua Nopalia lata 140 g", "atun latita de atun", "abarrotes", "caja con 24 latas", "456.00"),
    ("ABA-004", "Aceite vegetal Nopalia 1 L", "aceite de cocina aceite comestible", "abarrotes", "caja con 12 botellas", "420.00"),
    ("ABA-005", "Arroz súper extra Nopalia 1 kg", "arroz", "abarrotes", "bulto con 10 bolsas", "265.00"),
    ("ABA-006", "Azúcar estándar Nopalia 1 kg", "azucar morena azúcar", "abarrotes", "bulto con 10 bolsas", "289.00"),
    ("ABA-007", "Harina de maíz nixtamalizado Nopalia 1 kg", "harina para tortillas masa harina de maiz", "abarrotes", "bulto con 10 bolsas", "214.00"),
    ("ABA-008", "Chiles jalapeños en escabeche Nopalia 220 g", "chiles en lata jalapeños rajas", "abarrotes", "caja con 24 latas", "336.00"),
    ("ABA-009", "Salsa picante Nopalia 150 ml", "salsita picante chilito salsa botella", "abarrotes", "caja con 24 botellas", "264.00"),
    ("ABA-010", "Café soluble Nopalia 120 g", "cafe de frasco cafecito cafe instantaneo", "abarrotes", "caja con 12 frascos", "780.00"),
    ("GAL-001", "Galletas María Nopalia 170 g", "galletas maria marías galletitas", "galletas", "caja con 20 paquetes", "250.00"),
    ("GAL-002", "Galletas sándwich de chocolate Nopalia 117 g", "galletas de chocolate con crema galletas negras", "galletas", "caja con 24 paquetes", "336.00"),
    ("DUL-001", "Mazapán de cacahuate Nopalia 28 g", "mazapan mazapanes", "dulces", "exhibidor con 30 piezas", "120.00"),
    ("DUL-002", "Paleta de caramelo con chile Nopalia", "paletas enchiladas paletita de chile", "dulces", "bolsa con 40 piezas", "98.00"),
    ("LAC-001", "Leche entera ultrapasteurizada Nopalia 1 L", "leche de caja lechita leche entera", "lácteos", "caja con 12 piezas", "312.00"),
    ("LIM-001", "Papel higiénico Nopalia 4 rollos", "papel de baño rollos", "limpieza", "bulto con 12 paquetes", "396.00"),
    ("LIM-002", "Detergente en polvo Nopalia 1 kg", "jabon en polvo para ropa detergente", "limpieza", "caja con 10 bolsas", "345.00"),
    ("LIM-003", "Jabón de barra para ropa Nopalia 400 g", "jabon de pasta jabon de barra jabon para lavar", "limpieza", "caja con 25 barras", "310.00"),
]  # fmt: skip

CITIES = [
    ("Monterrey", "Nuevo León"),
    ("Guadalupe", "Nuevo León"),
    ("San Nicolás de los Garza", "Nuevo León"),
    ("Apodaca", "Nuevo León"),
    ("Escobedo", "Nuevo León"),
    ("Santa Catarina", "Nuevo León"),
    ("Saltillo", "Coahuila"),
]
STORE_PREFIXES = ["Abarrotes", "Mini Súper", "Tienda", "Miscelánea", "Depósito"]
STORE_SUFFIXES = [
    "La Esperanza", "El Güero", "Don Chuy", "La Bendición", "Los Pinos", "San Judas",
    "Las Palmas", "La Güera", "El Porvenir", "Mary", "Doña Rosy", "El Compadre",
]  # fmt: skip
FIRST_NAMES = [
    "José", "María", "Juan", "Guadalupe", "Francisco", "Rosa", "Jesús", "Verónica",
    "Ramiro", "Leticia", "Héctor", "Alejandra", "Rogelio", "Norma", "Eduardo", "Yolanda",
]  # fmt: skip
LAST_NAMES = [
    "Treviño", "Garza", "Salinas", "Cantú", "Villarreal", "González", "Martínez",
    "Elizondo", "Leal", "Cavazos", "Hernández", "Rodríguez", "De la Fuente", "Montemayor",
]  # fmt: skip
DRIVERS = ["Rubén Ayala", "Martín Lozano", "Óscar Medina", "Adrián Charles", "Iván Peña"]
FAILURE_REASONS = [
    "Tienda cerrada al momento de la visita",
    "Unidad con falla mecánica",
    "Cliente no tenía efectivo para el pago contra entrega",
]


@dataclass(frozen=True)
class DemoStore:
    """Stores with fixed data that tests, agent tests and the demo script rely on."""

    code: str
    name: str
    owner: str
    phone: str
    city: str


DEMO_STORES = [
    DemoStore("10234", "Abarrotes Doña Lupe", "Guadalupe Treviño Salinas", "+528155501234", "Monterrey"),
    DemoStore("20518", "Mini Súper El Güero", "Rogelio Cantú Leal", "+528155502518", "Guadalupe"),
    DemoStore("31007", "Tienda La Esperanza", "Norma Elizondo Garza", "+528155503107", "San Nicolás de los Garza"),
]  # fmt: skip


class Seeder:
    def __init__(self, db: Session, today: date, tz: ZoneInfo, rng: random.Random) -> None:
        self.db, self.today, self.tz, self.rng = db, today, tz, rng
        self.products: dict[str, Product] = {}

    def at(self, d: date, hour: int) -> datetime:
        return datetime.combine(d, time(hour), tzinfo=self.tz)

    def add_products(self) -> None:
        for sku, name, terms, cat, unit, price in PRODUCTS:
            p = Product(
                sku=sku,
                name=name,
                search_terms=terms,
                category=cat,
                unit=unit,
                price_mxn=Decimal(price),
                active=True,
            )
            self.db.add(p)
            self.products[sku] = p
        self.db.flush()

    def add_order(
        self,
        customer: Customer,
        folio: int,
        promised: date,
        status: OrderStatus,
        lines: list[tuple[str, int]],
        delivery_status: DeliveryStatus | None = None,
        failure_reason: str | None = None,
    ) -> Order:
        items = [
            OrderItem(product_id=self.products[sku].id, quantity=qty,
                      unit_price_mxn=self.products[sku].price_mxn)
            for sku, qty in lines
        ]  # fmt: skip
        order = Order(
            folio=folio,
            customer_id=customer.id,
            status=status,
            channel="sales_rep",
            total_mxn=sum((i.unit_price_mxn * i.quantity for i in items), Decimal("0")),
            promised_date=promised,
            created_at=self.at(promised - timedelta(days=2), 11),
            items=items,
        )
        self.db.add(order)
        self.db.flush()
        if delivery_status is not None:
            start_hour = self.rng.choice([8, 9, 11, 14])
            self.db.add(
                Delivery(
                    order_id=order.id,
                    route_code=f"MTY-R{self.rng.randint(1, 40):02d}",
                    driver_name=self.rng.choice(DRIVERS),
                    status=delivery_status,
                    window_start=self.at(promised, start_hour),
                    window_end=self.at(promised, start_hour + 4),
                    delivered_at=(
                        self.at(promised, start_hour + 2)
                        if delivery_status is DeliveryStatus.DELIVERED
                        else None
                    ),
                    failure_reason=failure_reason,
                )
            )
        return order

    def add_demo_stores(self) -> None:
        usual = [("BOT-001", 2), ("BEB-001", 5), ("ABA-001", 3), ("GAL-001", 2), ("ABA-002", 1)]
        for i, s in enumerate(DEMO_STORES):
            c = Customer(
                customer_code=s.code, store_name=s.name, owner_name=s.owner, phone=s.phone,
                city=s.city, state="Nuevo León", credit_limit_mxn=Decimal("25000"),
                credit_used_mxn=Decimal("8400"),
            )  # fmt: skip
            self.db.add(c)
            self.db.flush()
            base = 4700 + i * 1000  # 47xx, 57xx, 67xx
            # Three past delivered orders with a stable "usual" basket.
            for k, days_ago in enumerate([21, 14, 7]):
                lines = [*usual, ("DUL-001", 1)] if k == 1 else usual
                self.add_order(c, base + k, self.today - timedelta(days=days_ago),
                               OrderStatus.DELIVERED, lines, DeliveryStatus.DELIVERED)  # fmt: skip
            # Yesterday: delivery failed (the "report a delivery problem" scenario).
            self.add_order(c, base + 15, self.today - timedelta(days=1), OrderStatus.OUT_FOR_DELIVERY,
                           [("BEB-003", 4), ("LAC-001", 2)], DeliveryStatus.FAILED,
                           FAILURE_REASONS[0])  # fmt: skip
            # Today: on the truck (the "¿dónde está mi pedido?" scenario).
            self.add_order(c, base + 21, self.today, OrderStatus.OUT_FOR_DELIVERY, usual,
                           DeliveryStatus.IN_TRANSIT)  # fmt: skip
            # Day after tomorrow: still being picked.
            self.add_order(c, base + 30, self.today + timedelta(days=2), OrderStatus.PICKING,
                           [("ABA-004", 2), ("ABA-005", 1)], DeliveryStatus.SCHEDULED)  # fmt: skip

    def add_random_stores(self, n: int) -> None:
        rng, skus = self.rng, list(self.products)
        folio = 8000
        for idx in range(n):
            city, state = rng.choice(CITIES)
            owner = (f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)} "
                     f"{rng.choice(LAST_NAMES)}")  # fmt: skip
            c = Customer(
                customer_code=str(40000 + idx * 7),
                store_name=f"{rng.choice(STORE_PREFIXES)} {rng.choice(STORE_SUFFIXES)}",
                owner_name=owner,
                phone=f"+52815560{idx:04d}",
                city=city,
                state=state,
                credit_limit_mxn=Decimal(rng.choice([10000, 15000, 25000, 40000])),
                credit_used_mxn=Decimal(rng.randint(0, 9000)),
            )
            self.db.add(c)
            self.db.flush()
            for _ in range(rng.randint(2, 6)):
                offset = rng.randint(-30, 3)
                promised = self.today + timedelta(days=offset)
                dstatus: DeliveryStatus | None
                if offset < 0:
                    status, dstatus = OrderStatus.DELIVERED, DeliveryStatus.DELIVERED
                elif offset == 0:
                    status, dstatus = OrderStatus.OUT_FOR_DELIVERY, DeliveryStatus.IN_TRANSIT
                else:
                    status, dstatus = OrderStatus.PICKING, DeliveryStatus.SCHEDULED
                if rng.random() < 0.05:
                    status, dstatus = OrderStatus.CANCELLED, None
                lines = [(sku, rng.randint(1, 6)) for sku in rng.sample(skus, rng.randint(2, 6))]
                self.add_order(c, folio, promised, status, lines, dstatus)
                folio += 1


def seed(db: Session, *, today: date | None = None, random_stores: int = 40) -> None:
    tz = ZoneInfo(get_settings().timezone)
    today = today or datetime.now(tz).date()
    db.execute(
        text("TRUNCATE deliveries, order_items, orders, products, customers RESTART IDENTITY")
    )
    s = Seeder(db, today, tz, random.Random(42))
    s.add_products()
    s.add_demo_stores()
    s.add_random_stores(random_stores)
    db.commit()


def main() -> None:
    settings = get_settings()
    if settings.environment not in {"local", "test"}:
        raise SystemExit(f"Refusing to seed environment {settings.environment!r}")
    with Session(get_engine()) as db:
        seed(db)
    print("Seeded fictional data. Demo stores:", ", ".join(s.code for s in DEMO_STORES))


if __name__ == "__main__":
    main()
