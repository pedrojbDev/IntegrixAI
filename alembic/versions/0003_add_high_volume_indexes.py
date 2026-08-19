"""add high volume query indexes

Revision ID: 0003_add_high_volume_indexes
Revises: 0002_add_vapi_cost_tables
Create Date: 2026-05-06 00:00:00

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0003_add_high_volume_indexes"
down_revision = "0002_add_vapi_cost_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_call_events_tenant_event_created",
        "call_events",
        ["tenant_id", "event_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_call_events_tenant_event_call_created",
        "call_events",
        ["tenant_id", "event_type", "call_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_vapi_call_costs_tenant_synced",
        "vapi_call_costs",
        ["tenant_id", "synced_at"],
        unique=False,
    )
    op.create_index(
        "ix_vapi_call_costs_tenant_assistant_synced",
        "vapi_call_costs",
        ["tenant_id", "assistant_id", "synced_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_vapi_call_costs_tenant_assistant_synced", table_name="vapi_call_costs")
    op.drop_index("ix_vapi_call_costs_tenant_synced", table_name="vapi_call_costs")
    op.drop_index("ix_call_events_tenant_event_call_created", table_name="call_events")
    op.drop_index("ix_call_events_tenant_event_created", table_name="call_events")
