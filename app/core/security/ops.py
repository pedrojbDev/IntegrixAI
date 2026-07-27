from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from ...config import Settings, get_settings
from ...db import get_db
from ...models.ops_auth import OpsAuthEvent, OpsSession, OpsUser, OpsUserTenant

OPS_SESSION_COOKIE_NAME = "integrix_ops_session"
OPS_CSRF_COOKIE_NAME = "integrix_ops_csrf"
_PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


@dataclass(frozen=True)
class OpsPrincipal:
    id: str
    email: str
    role: str
    tenant_ids: tuple[str, ...]
    must_change_password: bool
    session_token_hash: str
    csrf_hash: str

    @property
    def is_platform_admin(self) -> bool:
        return self.role == "platform_admin"


def normalize_email(value: str) -> str:
    return value.strip().lower()


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def generate_temporary_password() -> str:
    return f"Ix!{secrets.token_urlsafe(12)}"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _auth_fingerprints(request: Request, email: str) -> tuple[str, str]:
    return _digest(normalize_email(email)), _digest(_client_ip(request))


def record_auth_event(
    session: Session,
    *,
    event_type: str,
    success: bool,
    user_id: str | None = None,
    tenant_id: str | None = None,
    principal_hint_hash: str | None = None,
    ip_hash: str | None = None,
    details: dict | None = None,
) -> None:
    session.add(
        OpsAuthEvent(
            event_type=event_type,
            success=success,
            user_id=user_id,
            tenant_id=tenant_id,
            principal_hint_hash=principal_hint_hash,
            ip_hash=ip_hash,
            details_json=details or {},
        )
    )


def enforce_login_rate_limit(
    session: Session,
    request: Request,
    email: str,
    settings: Settings,
) -> tuple[str, str]:
    hint_hash, ip_hash = _auth_fingerprints(request, email)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.ops_login_window_minutes)
    last_success = session.execute(
        select(func.max(OpsAuthEvent.created_at)).where(
            OpsAuthEvent.event_type == "login",
            OpsAuthEvent.success.is_(True),
            OpsAuthEvent.principal_hint_hash == hint_hash,
        )
    ).scalar()
    if last_success is not None and _as_utc(last_success) > cutoff:
        cutoff = _as_utc(last_success)
    failures = int(
        session.execute(
            select(func.count(OpsAuthEvent.id)).where(
                OpsAuthEvent.created_at >= cutoff,
                OpsAuthEvent.success.is_(False),
                OpsAuthEvent.event_type == "login",
                or_(
                    OpsAuthEvent.principal_hint_hash == hint_hash,
                    OpsAuthEvent.ip_hash == ip_hash,
                ),
            )
        ).scalar()
        or 0
    )
    if failures >= settings.ops_login_max_attempts:
        record_auth_event(
            session,
            event_type="login_blocked",
            success=False,
            principal_hint_hash=hint_hash,
            ip_hash=ip_hash,
        )
        session.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts")
    return hint_hash, ip_hash


def authenticate_user(
    session: Session,
    request: Request,
    email: str,
    password: str,
    settings: Settings,
) -> OpsUser:
    normalized = normalize_email(email)
    hint_hash, ip_hash = enforce_login_rate_limit(session, request, normalized, settings)
    user = session.execute(select(OpsUser).where(OpsUser.email == normalized)).scalar_one_or_none()
    valid = bool(user and user.is_active and verify_password(user.password_hash, password))
    record_auth_event(
        session,
        event_type="login",
        success=valid,
        user_id=user.id if user else None,
        principal_hint_hash=hint_hash,
        ip_hash=ip_hash,
    )
    session.commit()
    if not valid or user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if _PASSWORD_HASHER.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        session.commit()
    return user


def create_ops_session(
    session: Session,
    response: Response,
    user: OpsUser,
    settings: Settings,
) -> OpsPrincipal:
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    token_hash = _digest(raw_token)
    csrf_hash = _digest(csrf_token)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.ops_session_max_age_seconds)
    session.add(
        OpsSession(
            token_hash=token_hash,
            csrf_hash=csrf_hash,
            user_id=user.id,
            expires_at=expires_at,
        )
    )
    session.commit()
    response.set_cookie(
        OPS_SESSION_COOKIE_NAME,
        raw_token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.ops_session_max_age_seconds,
        expires=expires_at,
        path="/",
    )
    response.set_cookie(
        OPS_CSRF_COOKIE_NAME,
        csrf_token,
        httponly=False,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.ops_session_max_age_seconds,
        expires=expires_at,
        path="/",
    )
    session.refresh(user)
    return _principal_from_user(user, token_hash, csrf_hash)


def clear_ops_session_cookies(response: Response, settings: Settings) -> None:
    for cookie_name in (OPS_SESSION_COOKIE_NAME, OPS_CSRF_COOKIE_NAME):
        response.delete_cookie(
            cookie_name,
            secure=settings.is_production,
            samesite="lax",
            path="/",
        )


def _principal_from_user(user: OpsUser, token_hash: str, csrf_hash: str) -> OpsPrincipal:
    return OpsPrincipal(
        id=user.id,
        email=user.email,
        role=user.role,
        tenant_ids=tuple(sorted(membership.tenant_id for membership in user.memberships)),
        must_change_password=user.must_change_password,
        session_token_hash=token_hash,
        csrf_hash=csrf_hash,
    )


def require_ops_principal(
    request: Request,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db),
) -> OpsPrincipal:
    raw_token = request.cookies.get(OPS_SESSION_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    token_hash = _digest(raw_token)
    row = session.get(OpsSession, token_hash)
    now = datetime.now(timezone.utc)
    if row is None or row.revoked_at is not None or _as_utc(row.expires_at) <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user = session.get(OpsUser, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalid")
    principal = _principal_from_user(user, token_hash, row.csrf_hash)
    request.state.ops_principal = principal
    return principal


def require_ready_principal(
    principal: OpsPrincipal = Depends(require_ops_principal),
) -> OpsPrincipal:
    if principal.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change required",
        )
    return principal


def require_platform_admin(
    principal: OpsPrincipal = Depends(require_ready_principal),
) -> OpsPrincipal:
    if not principal.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return principal


def require_csrf(
    request: Request,
    principal: OpsPrincipal = Depends(require_ops_principal),
) -> OpsPrincipal:
    supplied = request.headers.get("x-csrf-token")
    if not supplied or not hmac.compare_digest(_digest(supplied), principal.csrf_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
    origin = request.headers.get("origin")
    if not origin or origin.rstrip("/").split("://", 1)[-1] != request.url.netloc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid request origin")
    return principal


def authorize_tenant_scope(
    principal: OpsPrincipal,
    requested_tenant_id: str | None,
    settings: Settings,
) -> str | None:
    requested = requested_tenant_id.strip() if requested_tenant_id else None
    if principal.is_platform_admin:
        if requested:
            return requested
        if settings.ops_allow_global_queries:
            return None
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tenant_id obrigatorio")
    if requested:
        if requested not in principal.tenant_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")
        return requested
    if len(principal.tenant_ids) == 1:
        return principal.tenant_ids[0]
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tenant_id obrigatorio")


def revoke_session(session: Session, principal: OpsPrincipal) -> None:
    row = session.get(OpsSession, principal.session_token_hash)
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)


def revoke_user_sessions(session: Session, user_id: str) -> None:
    session.execute(
        update(OpsSession)
        .where(OpsSession.user_id == user_id, OpsSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )


def set_user_tenants(session: Session, user: OpsUser, tenant_ids: list[str]) -> None:
    user.memberships.clear()
    session.flush()
    user.memberships.extend(
        OpsUserTenant(user_id=user.id, tenant_id=tenant_id)
        for tenant_id in sorted(set(tenant_ids))
    )


def user_to_dict(user: OpsUser) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "tenant_ids": sorted(membership.tenant_id for membership in user.memberships),
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }
