from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def _uuid_hex() -> str:
    return uuid4().hex


class OpsUser(Base):
    __tablename__ = "ops_users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('platform_admin', 'tenant_user')",
            name="ck_ops_users_role",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid_hex)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    memberships: Mapped[list["OpsUserTenant"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )


class OpsUserTenant(Base):
    __tablename__ = "ops_user_tenants"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_ops_user_tenant"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("ops_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[OpsUser] = relationship(back_populates="memberships")


class OpsSession(Base):
    __tablename__ = "ops_sessions"
    __table_args__ = (Index("ix_ops_sessions_user_expires", "user_id", "expires_at"),)

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("ops_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OpsAuthEvent(Base):
    __tablename__ = "ops_auth_events"
    __table_args__ = (
        Index("ix_ops_auth_events_hint_created", "principal_hint_hash", "created_at"),
        Index("ix_ops_auth_events_ip_created", "ip_hash", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    principal_hint_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
