from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..db import Base


class VapiCallCost(Base):
    __tablename__ = "vapi_call_costs"
    __table_args__ = (
        Index("ix_vapi_call_costs_tenant_synced", "tenant_id", "synced_at"),
        Index(
            "ix_vapi_call_costs_tenant_assistant_synced",
            "tenant_id",
            "assistant_id",
            "synced_at",
        ),
        Index("ix_vapi_call_costs_tenant_started", "tenant_id", "started_at"),
        Index(
            "ix_vapi_call_costs_tenant_assistant_started",
            "tenant_id",
            "assistant_id",
            "started_at",
        ),
        Index("ix_vapi_call_costs_vapi_updated", "vapi_updated_at"),
        Index("uq_vapi_call_costs_voice_call", "voice_call_id", unique=True),
    )

    call_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    voice_call_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("voice_calls.id", ondelete="RESTRICT"),
        nullable=True,
    )
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    to_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    phone_number_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tenant_resolution_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vapi_created_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vapi_updated_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    ended_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    assistant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    cost_total_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    cost_transport_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    cost_stt_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    cost_llm_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    cost_tts_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    cost_vapi_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    cost_analysis_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    cost_other_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    cost_breakdown_json: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=True
    )
    raw_call_json: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=True
    )
    fx_rate_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    usd_brl_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    cost_total_brl: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    fx_is_provisional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    synced_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
