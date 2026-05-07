from sqlalchemy import DateTime, Float, Index, String, func
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
    )

    call_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    to_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    ended_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    assistant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    cost_total_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_breakdown_json: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=True
    )
    synced_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
