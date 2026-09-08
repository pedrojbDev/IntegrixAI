"""Short-lived, tenant-scoped provider search results; query inputs are HMAC only."""
from datetime import datetime
from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON
from ..db import Base


class VapiSearchExecution(Base):
    __tablename__ = 'vapi_search_executions'
    __table_args__ = (Index('ix_vapi_search_expires', 'expires_at'),)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    call_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    query_hmac: Mapped[str] = mapped_column(String(64), primary_key=True)
    refresh_hmac: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    result_payload: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSON, 'sqlite'))
    final_state: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
