from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..db import Base


class VapiWebhookReceipt(Base):
    """Idempotent Vapi event inbox that never stores the original payload."""

    __tablename__ = "vapi_webhook_receipts"
    __table_args__ = (
        Index("ix_vapi_webhook_receipts_tenant_received", "tenant_id", "received_at"),
        Index("ix_vapi_webhook_receipts_call", "tenant_id", "provider_call_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    receipt_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_org_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_call_id: Mapped[str] = mapped_column(String(255), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False)
    identity_result: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_sanitized: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False, default=dict
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
