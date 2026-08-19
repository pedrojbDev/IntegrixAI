"""add tenant and provider resource ownership foundation

Revision ID: 0008_tenant_ownership
Revises: 0007_call_events_jsonb
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_tenant_ownership"
down_revision = "0007_call_events_jsonb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("implementation_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tenants_status", "tenants", ["status"], unique=False)
    op.execute(
        """
        INSERT INTO tenants (id, display_name, implementation_key, status)
        VALUES ('pbsaude', 'PB Saúde', 'pbsaude', 'active')
        ON CONFLICT (id) DO NOTHING
        """
    )

    op.create_table(
        "provider_resources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_org_id", sa.String(length=128), nullable=False),
        sa.Column("resource_kind", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=512), nullable=False),
        sa.Column("normalized_value", sa.String(length=512), nullable=True),
        sa.Column("telephony_credential_id", sa.String(length=160), nullable=True),
        sa.Column(
            "configuration_source",
            sa.String(length=32),
            nullable=False,
            server_default="manual",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_org_id",
            "resource_kind",
            "external_id",
            name="uq_provider_resource_external_identity",
        ),
    )
    op.create_table(
        "provider_resource_ownerships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider_resource_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["provider_resource_id"], ["provider_resources.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_provider_resource_active_ownership",
        "provider_resource_ownerships",
        ["provider_resource_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "ix_provider_ownership_resource_validity",
        "provider_resource_ownerships",
        ["provider_resource_id", "valid_from", "valid_to"],
        unique=False,
    )
    op.create_index(
        "ix_provider_ownership_tenant_validity",
        "provider_resource_ownerships",
        ["tenant_id", "valid_from", "valid_to"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_ownership_tenant_validity",
        table_name="provider_resource_ownerships",
    )
    op.drop_index(
        "ix_provider_ownership_resource_validity",
        table_name="provider_resource_ownerships",
    )
    op.drop_index(
        "uq_provider_resource_active_ownership",
        table_name="provider_resource_ownerships",
    )
    op.drop_table("provider_resource_ownerships")
    op.drop_table("provider_resources")
    op.drop_index("ix_tenants_status", table_name="tenants")
    op.drop_table("tenants")
