import uuid

from sqlalchemy import Boolean, DateTime, Float, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..db import Base


class ToolInvocationResult(Base):
    __tablename__ = "tool_invocation_results"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "call_id",
            "tool_call_id",
            name="uq_tool_invocation_results_tenant_call_toolcall",
        ),
        Index("ix_tool_invocation_results_tenant_call", "tenant_id", "call_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    call_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    final_state: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_payload: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ToolBusinessErrorAttempt(Base):
    __tablename__ = "tool_business_error_attempts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "call_id",
            "tool_name",
            "field",
            "upstream_code",
            name="uq_tool_business_error_attempts_scope",
        ),
        Index("ix_tool_business_error_attempts_tenant_call", "tenant_id", "call_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    call_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    upstream_code: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
