import uuid

from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class CallEvent(Base):
    __tablename__ = "call_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    call_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    final_state: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_masked: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=True
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

