from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class OpsSyncState(Base):
    __tablename__ = "ops_sync_state"

    provider: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_synced_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

