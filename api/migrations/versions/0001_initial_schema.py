"""initial schema: customers, products, orders, order_items, deliveries

Revision ID: 0001
Revises:
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fuzzy, accent-insensitive product search ("galletas maria" -> "Galletas María").
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("customer_code", sa.String(10), nullable=False),
        sa.Column("store_name", sa.String(120), nullable=False),
        sa.Column("owner_name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("city", sa.String(80), nullable=False),
        sa.Column("state", sa.String(80), nullable=False),
        sa.Column("credit_limit_mxn", sa.Numeric(12, 2), nullable=False),
        sa.Column("credit_used_mxn", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_customers_customer_code", "customers", ["customer_code"], unique=True)
    op.create_index("ix_customers_phone", "customers", ["phone"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sku", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("search_terms", sa.String(400), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("unit", sa.String(60), nullable=False),
        sa.Column("price_mxn", sa.Numeric(10, 2), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("folio", sa.Integer, nullable=False),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("total_mxn", sa.Numeric(12, 2), nullable=False),
        sa.Column("promised_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_orders_folio", "orders", ["folio"], unique=True)
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "order_id",
            sa.Integer,
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price_mxn", sa.Numeric(10, 2), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    op.create_table(
        "deliveries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id"), nullable=False, unique=True),
        sa.Column("route_code", sa.String(20), nullable=False),
        sa.Column("driver_name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("deliveries")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("products")
    op.drop_table("customers")
