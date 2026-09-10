"""add privacy-preserving Vapi voice quality metrics

Revision ID: 0013_vapi_voice_quality
Revises: 0012_vapi_search_execution
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_vapi_voice_quality"
down_revision = "0012_vapi_search_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vapi_call_costs",
        sa.Column("turn_latency_average_ms", sa.Float(), nullable=True),
    )
    op.add_column(
        "vapi_call_costs",
        sa.Column("assistant_interruptions", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vapi_call_costs", "assistant_interruptions")
    op.drop_column("vapi_call_costs", "turn_latency_average_ms")
