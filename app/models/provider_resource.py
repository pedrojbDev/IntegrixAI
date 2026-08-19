from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _uuid() -> str:
    return str(uuid4())


class ProviderResource(Base):
    """Stable identity of a tenant-resolving resource in a voice provider."""

    __tablename__ = "provider_resources"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_org_id",
            "resource_kind",
            "external_id",
            name="uq_provider_resource_external_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_org_id: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    telephony_credential_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    configuration_source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProviderResourceOwnership(Base):
    """Temporal and append-preserving ownership of a provider resource."""

    __tablename__ = "provider_resource_ownerships"
    __table_args__ = (
        Index(
            "uq_provider_resource_active_ownership",
            "provider_resource_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
            sqlite_where=text("valid_to IS NULL"),
        ),
        Index(
            "ix_provider_ownership_resource_validity",
            "provider_resource_id",
            "valid_from",
            "valid_to",
        ),
        Index(
            "ix_provider_ownership_tenant_validity",
            "tenant_id",
            "valid_from",
            "valid_to",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider_resource_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("provider_resources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
