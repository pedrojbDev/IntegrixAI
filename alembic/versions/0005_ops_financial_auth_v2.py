"""add ops financial and authentication v2

Revision ID: 0005_ops_financial_auth_v2
Revises: 0004_add_tool_idempotency
Create Date: 2026-07-24 00:00:00

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0005_ops_financial_auth_v2"
down_revision = "0004_add_tool_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ops_users",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), server_default=sa.true(), nullable=False),
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
        sa.CheckConstraint(
            "role IN ('platform_admin', 'tenant_user')",
            name="ck_ops_users_role",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ops_users_email", "ops_users", ["email"], unique=True)
    op.create_index("ix_ops_users_role", "ops_users", ["role"], unique=False)

    op.create_table(
        "ops_user_tenants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["ops_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_ops_user_tenant"),
    )
    op.create_index("ix_ops_user_tenants_user_id", "ops_user_tenants", ["user_id"], unique=False)
    op.create_index("ix_ops_user_tenants_tenant_id", "ops_user_tenants", ["tenant_id"], unique=False)

    op.create_table(
        "ops_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["ops_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_ops_sessions_user_id", "ops_sessions", ["user_id"], unique=False)
    op.create_index("ix_ops_sessions_expires_at", "ops_sessions", ["expires_at"], unique=False)
    op.create_index(
        "ix_ops_sessions_user_expires",
        "ops_sessions",
        ["user_id", "expires_at"],
        unique=False,
    )

    op.create_table(
        "ops_auth_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("principal_hint_hash", sa.String(length=64), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ops_auth_events_user_id", "ops_auth_events", ["user_id"], unique=False)
    op.create_index("ix_ops_auth_events_tenant_id", "ops_auth_events", ["tenant_id"], unique=False)
    op.create_index("ix_ops_auth_events_event_type", "ops_auth_events", ["event_type"], unique=False)
    op.create_index("ix_ops_auth_events_created_at", "ops_auth_events", ["created_at"], unique=False)
    op.create_index(
        "ix_ops_auth_events_hint_created",
        "ops_auth_events",
        ["principal_hint_hash", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ops_auth_events_ip_created",
        "ops_auth_events",
        ["ip_hash", "created_at"],
        unique=False,
    )

    op.create_table(
        "exchange_rates",
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("quote_currency", sa.String(length=3), nullable=False),
        sa.Column("sale_rate", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("is_provisional", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("rate_date", "base_currency", "quote_currency"),
    )

    op.add_column(
        "ops_sync_state",
        sa.Column("cursor_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ops_sync_state",
        sa.Column("last_successful_run_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("ops_sync_state", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("ops_sync_state", sa.Column("last_run_stats_json", sa.JSON(), nullable=True))
    op.add_column(
        "ops_sync_state",
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        "UPDATE ops_sync_state "
        "SET cursor_updated_at = last_synced_at, last_successful_run_at = last_synced_at"
    )

    op.alter_column("vapi_call_costs", "tenant_id", existing_type=sa.String(64), nullable=True)
    op.alter_column(
        "vapi_call_costs",
        "cost_total_usd",
        existing_type=sa.Float(),
        type_=sa.Numeric(18, 8),
        existing_nullable=True,
        postgresql_using="cost_total_usd::numeric(18,8)",
    )
    op.alter_column(
        "vapi_call_costs",
        "cost_breakdown_json",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(),
        existing_nullable=True,
        postgresql_using="cost_breakdown_json::jsonb",
    )
    op.add_column("vapi_call_costs", sa.Column("phone_number_id", sa.String(64), nullable=True))
    op.add_column(
        "vapi_call_costs",
        sa.Column("tenant_resolution_source", sa.String(64), nullable=True),
    )
    op.add_column(
        "vapi_call_costs",
        sa.Column("vapi_created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "vapi_call_costs",
        sa.Column("vapi_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    for name in (
        "cost_transport_usd",
        "cost_stt_usd",
        "cost_llm_usd",
        "cost_tts_usd",
        "cost_vapi_usd",
        "cost_analysis_usd",
        "cost_other_usd",
    ):
        op.add_column(
            "vapi_call_costs",
            sa.Column(name, sa.Numeric(precision=18, scale=8), nullable=True),
        )
    op.add_column(
        "vapi_call_costs",
        sa.Column("raw_call_json", postgresql.JSONB(), nullable=True),
    )
    op.add_column("vapi_call_costs", sa.Column("fx_rate_date", sa.Date(), nullable=True))
    op.add_column(
        "vapi_call_costs",
        sa.Column("usd_brl_rate", sa.Numeric(precision=18, scale=8), nullable=True),
    )
    op.add_column(
        "vapi_call_costs",
        sa.Column("cost_total_brl", sa.Numeric(precision=18, scale=8), nullable=True),
    )
    op.add_column(
        "vapi_call_costs",
        sa.Column("fx_is_provisional", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "vapi_call_costs",
        sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index(
        "ix_vapi_call_costs_phone_number_id",
        "vapi_call_costs",
        ["phone_number_id"],
        unique=False,
    )
    op.create_index(
        "ix_vapi_call_costs_fx_rate_date",
        "vapi_call_costs",
        ["fx_rate_date"],
        unique=False,
    )
    op.create_index(
        "ix_vapi_call_costs_tenant_started",
        "vapi_call_costs",
        ["tenant_id", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_vapi_call_costs_tenant_assistant_started",
        "vapi_call_costs",
        ["tenant_id", "assistant_id", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_vapi_call_costs_vapi_updated",
        "vapi_call_costs",
        ["vapi_updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_vapi_call_costs_vapi_updated", table_name="vapi_call_costs")
    op.drop_index("ix_vapi_call_costs_tenant_assistant_started", table_name="vapi_call_costs")
    op.drop_index("ix_vapi_call_costs_tenant_started", table_name="vapi_call_costs")
    op.drop_index("ix_vapi_call_costs_fx_rate_date", table_name="vapi_call_costs")
    op.drop_index("ix_vapi_call_costs_phone_number_id", table_name="vapi_call_costs")
    for name in (
        "is_verified",
        "fx_is_provisional",
        "cost_total_brl",
        "usd_brl_rate",
        "fx_rate_date",
        "raw_call_json",
        "cost_other_usd",
        "cost_analysis_usd",
        "cost_vapi_usd",
        "cost_tts_usd",
        "cost_llm_usd",
        "cost_stt_usd",
        "cost_transport_usd",
        "vapi_updated_at",
        "vapi_created_at",
        "tenant_resolution_source",
        "phone_number_id",
    ):
        op.drop_column("vapi_call_costs", name)
    op.alter_column(
        "vapi_call_costs",
        "cost_total_usd",
        existing_type=sa.Numeric(18, 8),
        type_=sa.Float(),
        existing_nullable=True,
        postgresql_using="cost_total_usd::double precision",
    )
    op.alter_column(
        "vapi_call_costs",
        "cost_breakdown_json",
        existing_type=postgresql.JSONB(),
        type_=sa.JSON(),
        existing_nullable=True,
        postgresql_using="cost_breakdown_json::json",
    )
    op.execute("DELETE FROM vapi_call_costs WHERE tenant_id IS NULL")
    op.alter_column("vapi_call_costs", "tenant_id", existing_type=sa.String(64), nullable=False)

    for name in (
        "consecutive_failures",
        "last_run_stats_json",
        "last_error",
        "last_successful_run_at",
        "cursor_updated_at",
    ):
        op.drop_column("ops_sync_state", name)

    op.drop_table("exchange_rates")
    op.drop_index("ix_ops_auth_events_ip_created", table_name="ops_auth_events")
    op.drop_index("ix_ops_auth_events_hint_created", table_name="ops_auth_events")
    op.drop_index("ix_ops_auth_events_created_at", table_name="ops_auth_events")
    op.drop_index("ix_ops_auth_events_event_type", table_name="ops_auth_events")
    op.drop_index("ix_ops_auth_events_tenant_id", table_name="ops_auth_events")
    op.drop_index("ix_ops_auth_events_user_id", table_name="ops_auth_events")
    op.drop_table("ops_auth_events")
    op.drop_index("ix_ops_sessions_user_expires", table_name="ops_sessions")
    op.drop_index("ix_ops_sessions_expires_at", table_name="ops_sessions")
    op.drop_index("ix_ops_sessions_user_id", table_name="ops_sessions")
    op.drop_table("ops_sessions")
    op.drop_index("ix_ops_user_tenants_tenant_id", table_name="ops_user_tenants")
    op.drop_index("ix_ops_user_tenants_user_id", table_name="ops_user_tenants")
    op.drop_table("ops_user_tenants")
    op.drop_index("ix_ops_users_role", table_name="ops_users")
    op.drop_index("ix_ops_users_email", table_name="ops_users")
    op.drop_table("ops_users")
