"""migrate masked call event payloads to jsonb

Revision ID: 0007_call_events_jsonb
Revises: 0006_reset_vapi_cursor
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0007_call_events_jsonb"
down_revision = "0006_reset_vapi_cursor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "call_events",
        "payload_masked",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(),
        existing_nullable=True,
        postgresql_using="payload_masked::jsonb",
    )


def downgrade() -> None:
    # Kept for disposable development/CI databases. Production rollbacks retain JSONB.
    op.alter_column(
        "call_events",
        "payload_masked",
        existing_type=postgresql.JSONB(),
        type_=sa.JSON(),
        existing_nullable=True,
        postgresql_using="payload_masked::json",
    )
