from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..db import Base


class ProviderEventReceipt(Base):
    """Immutable, sanitized inbox receipt for provider observations."""

    __tablename__ = "provider_event_receipts"
    __table_args__ = (
        UniqueConstraint("provider", "receipt_key", name="uq_provider_receipt_key"),
        Index(
            "ix_provider_receipts_call_received",
            "provider",
            "provider_call_id",
            "received_at",
        ),
        Index(
            "ix_provider_receipts_processing_received",
            "processing_status",
            "received_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    receipt_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_event_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provider_org_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    voice_call_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("voice_calls.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False)
    identity_result: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_sanitized: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False
    )
    provider_occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
