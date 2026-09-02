"""Add hashed turn evidence and recovery metadata without discarding active calls."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_vapi_conversation_state"
down_revision = "0010_vapi_slot_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vapi_call_slot_states", sa.Column(
        "conversation_meta", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
        nullable=False, server_default=sa.text("'{}'"),
    ))


def downgrade() -> None:
    op.drop_column("vapi_call_slot_states", "conversation_meta")
