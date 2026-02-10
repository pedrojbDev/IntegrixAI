"""create call_events

Revision ID: 0001_create_call_events
Revises:
Create Date: 2026-02-10 00:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_create_call_events"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "call_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("call_id", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("final_state", sa.String(length=64), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("payload_masked", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_call_events_tenant_id", "call_events", ["tenant_id"], unique=False)
    op.create_index("ix_call_events_call_id", "call_events", ["call_id"], unique=False)
    op.create_index("ix_call_events_tool_name", "call_events", ["tool_name"], unique=False)
    op.create_index("ix_call_events_event_type", "call_events", ["event_type"], unique=False)
    op.create_index("ix_call_events_final_state", "call_events", ["final_state"], unique=False)
    op.create_index("ix_call_events_ok", "call_events", ["ok"], unique=False)
    op.create_index("ix_call_events_created_at", "call_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_call_events_created_at", table_name="call_events")
    op.drop_index("ix_call_events_ok", table_name="call_events")
    op.drop_index("ix_call_events_final_state", table_name="call_events")
    op.drop_index("ix_call_events_event_type", table_name="call_events")
    op.drop_index("ix_call_events_tool_name", table_name="call_events")
    op.drop_index("ix_call_events_call_id", table_name="call_events")
    op.drop_index("ix_call_events_tenant_id", table_name="call_events")
    op.drop_table("call_events")

