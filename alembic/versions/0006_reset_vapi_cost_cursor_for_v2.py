"""reset legacy Vapi cursor for the financial v2 backfill

Revision ID: 0006_reset_vapi_cost_cursor_for_v2
Revises: 0005_ops_financial_auth_v2
Create Date: 2026-07-27
"""

from alembic import op


revision = "0006_reset_vapi_cost_cursor_for_v2"
down_revision = "0005_ops_financial_auth_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE ops_sync_state
        SET cursor_updated_at = NULL,
            last_error = NULL
        WHERE provider = 'vapi_costs'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE ops_sync_state
        SET cursor_updated_at = COALESCE(last_successful_run_at, last_synced_at)
        WHERE provider = 'vapi_costs'
          AND cursor_updated_at IS NULL
        """
    )
