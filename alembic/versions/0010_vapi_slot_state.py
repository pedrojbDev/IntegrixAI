"""add privacy-preserving Vapi slot provenance state

Revision ID: 0010_vapi_slot_state
Revises: 0009_voice_call_reconcile
Create Date: 2026-09-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010_vapi_slot_state"
down_revision = "0009_voice_call_reconcile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vapi_webhook_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("receipt_key", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("provider_org_id", sa.String(length=255), nullable=True),
        sa.Column("provider_call_id", sa.String(length=255), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("identity_result", sa.String(length=64), nullable=True),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload_sanitized", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("provider_occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_key"),
    )
    op.create_index("ix_vapi_webhook_receipts_tenant_received", "vapi_webhook_receipts", ["tenant_id", "received_at"], unique=False)
    op.create_index("ix_vapi_webhook_receipts_call", "vapi_webhook_receipts", ["tenant_id", "provider_call_id"], unique=False)
    op.create_table(
        "vapi_call_slot_states",
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("call_id", sa.String(length=128), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False, server_default="cpf"),
        sa.Column("cpf_hmac", sa.String(length=64), nullable=True),
        sa.Column("city_term_hmacs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("specialty_term_hmacs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("processed_message_hmacs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "call_id"),
    )
    op.create_index("ix_vapi_slot_states_expires", "vapi_call_slot_states", ["expires_at"], unique=False)
    op.create_index("ix_vapi_slot_states_tenant_updated", "vapi_call_slot_states", ["tenant_id", "updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_vapi_slot_states_tenant_updated", table_name="vapi_call_slot_states")
    op.drop_index("ix_vapi_slot_states_expires", table_name="vapi_call_slot_states")
    op.drop_table("vapi_call_slot_states")
    op.drop_index("ix_vapi_webhook_receipts_call", table_name="vapi_webhook_receipts")
    op.drop_index("ix_vapi_webhook_receipts_tenant_received", table_name="vapi_webhook_receipts")
    op.drop_table("vapi_webhook_receipts")
