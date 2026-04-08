"""add vapi cost tables

Revision ID: 0002_add_vapi_cost_tables
Revises: 0001_create_call_events
Create Date: 2026-03-31 00:00:00

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_add_vapi_cost_tables"
down_revision = "0001_create_call_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vapi_call_costs",
        sa.Column("call_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("to_number", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("assistant_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("cost_total_usd", sa.Float(), nullable=True),
        sa.Column("cost_breakdown_json", sa.JSON(), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("call_id"),
    )
    op.create_index("ix_vapi_call_costs_tenant_id", "vapi_call_costs", ["tenant_id"], unique=False)
    op.create_index("ix_vapi_call_costs_to_number", "vapi_call_costs", ["to_number"], unique=False)
    op.create_index("ix_vapi_call_costs_started_at", "vapi_call_costs", ["started_at"], unique=False)
    op.create_index("ix_vapi_call_costs_assistant_id", "vapi_call_costs", ["assistant_id"], unique=False)
    op.create_index("ix_vapi_call_costs_status", "vapi_call_costs", ["status"], unique=False)
    op.create_index("ix_vapi_call_costs_synced_at", "vapi_call_costs", ["synced_at"], unique=False)

    op.create_table(
        "ops_sync_state",
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("provider"),
    )


def downgrade() -> None:
    op.drop_table("ops_sync_state")
    op.drop_index("ix_vapi_call_costs_synced_at", table_name="vapi_call_costs")
    op.drop_index("ix_vapi_call_costs_status", table_name="vapi_call_costs")
    op.drop_index("ix_vapi_call_costs_assistant_id", table_name="vapi_call_costs")
    op.drop_index("ix_vapi_call_costs_started_at", table_name="vapi_call_costs")
    op.drop_index("ix_vapi_call_costs_to_number", table_name="vapi_call_costs")
    op.drop_index("ix_vapi_call_costs_tenant_id", table_name="vapi_call_costs")
    op.drop_table("vapi_call_costs")

