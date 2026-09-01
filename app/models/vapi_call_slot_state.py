from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..db import Base


class VapiCallSlotState(Base):
    """Minimal, tenant-scoped slot provenance for an active Vapi call.

    The model deliberately stores only keyed hashes of user-provided values; it
    never stores a transcript, recording URL, or plaintext CPF.
    """

    __tablename__ = "vapi_call_slot_states"
    __table_args__ = (
        Index("ix_vapi_slot_states_expires", "expires_at"),
        Index("ix_vapi_slot_states_tenant_updated", "tenant_id", "updated_at"),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    call_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default="cpf")
    cpf_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city_term_hmacs: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list
    )
    specialty_term_hmacs: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list
    )
    processed_message_hmacs: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False, default=list
    )
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
