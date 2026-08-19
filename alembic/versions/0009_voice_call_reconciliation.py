"""add canonical inbound voice calls and provider receipt inbox

Revision ID: 0009_voice_call_reconcile
Revises: 0008_tenant_ownership
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009_voice_call_reconcile"
down_revision = "0008_tenant_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_org_id", sa.String(length=128), nullable=True),
        sa.Column("provider_call_id", sa.String(length=128), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False, server_default="inbound"),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("identity_status", sa.String(length=32), nullable=False),
        sa.Column("identity_source", sa.String(length=64), nullable=True),
        sa.Column("reconciliation_status", sa.String(length=32), nullable=False),
        sa.Column("identity_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_fixed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phone_number_id", sa.String(length=160), nullable=True),
        sa.Column("did", sa.String(length=64), nullable=True),
        sa.Column("telephony_credential_id", sa.String(length=160), nullable=True),
        sa.Column("assistant_id", sa.String(length=160), nullable=True),
        sa.Column("sip_destination", sa.String(length=512), nullable=True),
        sa.Column("provider_status", sa.String(length=64), nullable=True),
        sa.Column("provider_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_call_id", name="uq_voice_call_provider_call"
        ),
    )
    op.create_index("ix_voice_calls_tenant_id", "voice_calls", ["tenant_id"])
    op.create_index("ix_voice_calls_identity_status", "voice_calls", ["identity_status"])
    op.create_index(
        "ix_voice_calls_reconciliation_status",
        "voice_calls",
        ["reconciliation_status"],
    )
    op.create_index(
        "ix_voice_calls_tenant_started", "voice_calls", ["tenant_id", "started_at"]
    )
    op.create_index(
        "ix_voice_calls_identity_reconciliation_updated",
        "voice_calls",
        ["identity_status", "reconciliation_status", "updated_at"],
    )

    op.execute(
        """
        CREATE FUNCTION prevent_voice_call_tenant_reassignment()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.tenant_id IS NOT NULL
               AND NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
                RAISE EXCEPTION 'voice_call tenant_id is immutable once assigned';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_voice_call_tenant_immutable
        BEFORE UPDATE OF tenant_id ON voice_calls
        FOR EACH ROW
        EXECUTE FUNCTION prevent_voice_call_tenant_reassignment()
        """
    )

    op.create_table(
        "provider_event_receipts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("receipt_key", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("external_event_id", sa.String(length=160), nullable=True),
        sa.Column("provider_org_id", sa.String(length=128), nullable=True),
        sa.Column("provider_call_id", sa.String(length=128), nullable=True),
        sa.Column("voice_call_id", sa.String(length=36), nullable=True),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("identity_result", sa.String(length=32), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload_sanitized", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider_occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["voice_call_id"], ["voice_calls.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "receipt_key", name="uq_provider_receipt_key"),
    )
    op.create_index(
        "ix_provider_event_receipts_voice_call_id",
        "provider_event_receipts",
        ["voice_call_id"],
    )
    op.create_index(
        "ix_provider_receipts_call_received",
        "provider_event_receipts",
        ["provider", "provider_call_id", "received_at"],
    )
    op.create_index(
        "ix_provider_receipts_processing_received",
        "provider_event_receipts",
        ["processing_status", "received_at"],
    )

    op.add_column("vapi_call_costs", sa.Column("voice_call_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_vapi_call_costs_voice_call_id",
        "vapi_call_costs",
        "voice_calls",
        ["voice_call_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_vapi_call_costs_voice_call",
        "vapi_call_costs",
        ["voice_call_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_vapi_call_costs_voice_call", table_name="vapi_call_costs")
    op.drop_constraint(
        "fk_vapi_call_costs_voice_call_id", "vapi_call_costs", type_="foreignkey"
    )
    op.drop_column("vapi_call_costs", "voice_call_id")
    op.drop_index(
        "ix_provider_receipts_processing_received",
        table_name="provider_event_receipts",
    )
    op.drop_index(
        "ix_provider_receipts_call_received", table_name="provider_event_receipts"
    )
    op.drop_index(
        "ix_provider_event_receipts_voice_call_id",
        table_name="provider_event_receipts",
    )
    op.drop_table("provider_event_receipts")
    op.execute("DROP TRIGGER trg_voice_call_tenant_immutable ON voice_calls")
    op.execute("DROP FUNCTION prevent_voice_call_tenant_reassignment()")
    op.drop_index(
        "ix_voice_calls_identity_reconciliation_updated", table_name="voice_calls"
    )
    op.drop_index("ix_voice_calls_tenant_started", table_name="voice_calls")
    op.drop_index("ix_voice_calls_reconciliation_status", table_name="voice_calls")
    op.drop_index("ix_voice_calls_identity_status", table_name="voice_calls")
    op.drop_index("ix_voice_calls_tenant_id", table_name="voice_calls")
    op.drop_table("voice_calls")
