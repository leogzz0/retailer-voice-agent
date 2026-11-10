"""integration hardening: delivery zones, folio sequence, verification, idempotency,
incidents, handoff outbox, conversations

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    # Existing stores default to metro; ops reclassify foráneos afterwards.
    op.add_column(
        "customers",
        sa.Column("zone", sa.String(32), server_default="metro", nullable=False),
    )

    # New folios from a sequence, above any folio already issued.
    op.execute("CREATE SEQUENCE order_folio_seq START WITH 10000")
    op.execute(
        "SELECT setval('order_folio_seq', GREATEST(10000, COALESCE(MAX(folio), 0) + 1), false) "
        "FROM orders"
    )
    op.alter_column("orders", "folio", server_default=sa.text("nextval('order_folio_seq')"))

    op.create_table(
        "verification_attempts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("conversation_id", sa.String(128), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index(
        "ix_verification_attempts_customer_id", "verification_attempts", ["customer_id"]
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer, nullable=False),
        sa.Column("response_body", JSONB, nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("key", "operation", name="uq_idempotency_key_operation"),
    )

    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ticket_number", sa.String(20), unique=True, nullable=True),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("conversation_id", sa.String(128), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_incidents_customer_id", "incidents", ["customer_id"])

    op.create_table(
        "handoff_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("reference", sa.String(20), unique=True, nullable=True),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("summary", sa.String(1000), nullable=False),
        sa.Column("callback_phone", sa.String(20), nullable=True),
        sa.Column("conversation_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("external_ticket_id", sa.String(40), nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )
    op.create_index("ix_handoff_requests_customer_id", "handoff_requests", ["customer_id"])
    op.create_index("ix_handoff_requests_status", "handoff_requests", ["status"])

    op.create_table(
        "conversations",
        sa.Column("conversation_id", sa.String(128), primary_key=True),
        sa.Column("agent_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(40), nullable=True),
        sa.Column("call_duration_secs", sa.Integer, nullable=True),
        sa.Column("transcript_summary", sa.Text, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("received_at", TS, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("conversations")
    op.drop_table("handoff_requests")
    op.drop_table("incidents")
    op.drop_table("idempotency_keys")
    op.drop_table("verification_attempts")
    op.alter_column("orders", "folio", server_default=None)
    op.execute("DROP SEQUENCE order_folio_seq")
    op.drop_column("customers", "zone")
