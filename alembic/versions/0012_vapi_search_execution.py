"""Persist scoped provider-search execution and short-lived successful results."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0012_vapi_search_execution'
down_revision = '0011_vapi_conversation_state'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('vapi_search_executions',
        sa.Column('tenant_id', sa.String(64), primary_key=True),
        sa.Column('call_id', sa.String(128), primary_key=True),
        sa.Column('query_hmac', sa.String(64), primary_key=True),
        sa.Column('refresh_hmac', sa.String(64), primary_key=True),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('result_payload', postgresql.JSONB().with_variant(sa.JSON(), 'sqlite')),
        sa.Column('final_state', sa.String(64)),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_vapi_search_expires', 'vapi_search_executions', ['expires_at'])


def downgrade():
    op.drop_index('ix_vapi_search_expires', table_name='vapi_search_executions')
    op.drop_table('vapi_search_executions')
