"""add tool idempotency

Revision ID: 0004_add_tool_idempotency
Revises: 0003_add_high_volume_indexes
Create Date: 2026-05-07 00:00:00

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0004_add_tool_idempotency"
down_revision = "0003_add_high_volume_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("call_events", sa.Column("tool_call_id", sa.String(length=128), nullable=True))
    op.create_index("ix_call_events_tool_call_id", "call_events", ["tool_call_id"], unique=False)

    op.create_table(
        "tool_invocation_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("call_id", sa.String(length=64), nullable=False),
        sa.Column("tool_call_id", sa.String(length=128), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("final_state", sa.String(length=64), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("result_payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "call_id",
            "tool_call_id",
            name="uq_tool_invocation_results_tenant_call_toolcall",
        ),
    )
    op.create_index(
        "ix_tool_invocation_results_tenant_call",
        "tool_invocation_results",
        ["tenant_id", "call_id"],
        unique=False,
    )

    op.create_table(
        "tool_business_error_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("call_id", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("upstream_code", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "call_id",
            "tool_name",
            "field",
            "upstream_code",
            name="uq_tool_business_error_attempts_scope",
        ),
    )
    op.create_index(
        "ix_tool_business_error_attempts_tenant_call",
        "tool_business_error_attempts",
        ["tenant_id", "call_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tool_business_error_attempts_tenant_call", table_name="tool_business_error_attempts")
    op.drop_table("tool_business_error_attempts")
    op.drop_index("ix_tool_invocation_results_tenant_call", table_name="tool_invocation_results")
    op.drop_table("tool_invocation_results")
    op.drop_index("ix_call_events_tool_call_id", table_name="call_events")
    op.drop_column("call_events", "tool_call_id")
