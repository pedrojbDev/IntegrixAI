from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class OpsSyncState(Base):
    __tablename__ = "ops_sync_state"

    provider: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_synced_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    cursor_updated_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_run_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_stats_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
