from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _uuid() -> str:
    return str(uuid4())


class VoiceCall(Base):
    """Canonical inbound call identity with a tenant assignment fixed at most once."""

    __tablename__ = "voice_calls"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_call_id",
            name="uq_voice_call_provider_call",
        ),
        Index("ix_voice_calls_tenant_started", "tenant_id", "started_at"),
        Index(
            "ix_voice_calls_identity_reconciliation_updated",
            "identity_status",
            "reconciliation_status",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="vapi")
    provider_org_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="inbound")
    tenant_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    identity_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="quarantined", index=True
    )
    identity_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reconciliation_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )
    identity_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tenant_fixed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    phone_number_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    did: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telephony_credential_id: Mapped[str | None] = mapped_column(
        String(160), nullable=True
    )
    assistant_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sip_destination: Mapped[str | None] = mapped_column(String(512), nullable=True)
    provider_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provider_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
