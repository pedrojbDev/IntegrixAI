from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.security.ops import (
    OpsPrincipal,
    generate_temporary_password,
    hash_password,
    record_auth_event,
    require_csrf,
    require_platform_admin,
    revoke_user_sessions,
    set_user_tenants,
    user_to_dict,
)
from ...db import get_db
from ...models.ops_auth import OpsUser
from ...schemas.ops_auth import (
    OpsPasswordResetResponse,
    OpsUserCreate,
    OpsUserCreatedResponse,
    OpsUserResponse,
    OpsUserUpdate,
)

router = APIRouter(prefix="/ops/admin/users", tags=["ops-admin"])


def _admin_with_csrf(
    admin: OpsPrincipal = Depends(require_platform_admin),
    csrf: OpsPrincipal = Depends(require_csrf),
) -> OpsPrincipal:
    if admin.id != csrf.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Principal mismatch")
    return admin


@router.get("", response_model=list[OpsUserResponse])
async def list_ops_users(
    _: OpsPrincipal = Depends(require_platform_admin),
    session: Session = Depends(get_db),
):
    users = session.execute(select(OpsUser).order_by(OpsUser.email.asc())).scalars().all()
    return [user_to_dict(user) for user in users]


@router.post("", response_model=OpsUserCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_ops_user(
    payload: OpsUserCreate,
    admin: OpsPrincipal = Depends(_admin_with_csrf),
    session: Session = Depends(get_db),
):
    if session.execute(select(OpsUser.id).where(OpsUser.email == payload.email)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    if payload.role == "tenant_user" and not payload.tenant_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Tenant required")
    temporary_password = generate_temporary_password()
    user = OpsUser(
        email=payload.email,
        password_hash=hash_password(temporary_password),
        role=payload.role,
        is_active=True,
        must_change_password=True,
    )
    session.add(user)
    session.flush()
    set_user_tenants(session, user, payload.tenant_ids)
    record_auth_event(
        session,
        event_type="user_created",
        success=True,
        user_id=admin.id,
        details={"target_user_id": user.id, "role": user.role},
    )
    session.commit()
    session.refresh(user)
    return {"user": user_to_dict(user), "temporary_password": temporary_password}


@router.patch("/{user_id}", response_model=OpsUserResponse)
async def update_ops_user(
    user_id: str,
    payload: OpsUserUpdate,
    admin: OpsPrincipal = Depends(_admin_with_csrf),
    session: Session = Depends(get_db),
):
    user = session.get(OpsUser, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id and payload.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot disable own user")
    if user.id == admin.id and payload.role == "tenant_user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot demote own user")
    removes_active_admin = (
        user.role == "platform_admin"
        and user.is_active
        and (payload.role == "tenant_user" or payload.is_active is False)
    )
    if removes_active_admin:
        active_admins = int(
            session.execute(
                select(func.count(OpsUser.id)).where(
                    OpsUser.role == "platform_admin",
                    OpsUser.is_active.is_(True),
                )
            ).scalar()
            or 0
        )
        if active_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove last active administrator",
            )
    next_role = payload.role or user.role
    next_tenants = payload.tenant_ids if payload.tenant_ids is not None else [
        membership.tenant_id for membership in user.memberships
    ]
    if next_role == "tenant_user" and not next_tenants:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Tenant required")
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.tenant_ids is not None:
        set_user_tenants(session, user, payload.tenant_ids)
    if payload.role is not None or payload.is_active is not None or payload.tenant_ids is not None:
        revoke_user_sessions(session, user.id)
    event_type = "memberships_changed" if payload.tenant_ids is not None else "user_updated"
    if payload.is_active is False:
        event_type = "user_disabled"
    elif payload.is_active is True:
        event_type = "user_activated"
    record_auth_event(
        session,
        event_type=event_type,
        success=True,
        user_id=admin.id,
        details={"target_user_id": user.id},
    )
    session.commit()
    session.refresh(user)
    return user_to_dict(user)


@router.post("/{user_id}/reset-password", response_model=OpsPasswordResetResponse)
async def reset_ops_user_password(
    user_id: str,
    admin: OpsPrincipal = Depends(_admin_with_csrf),
    session: Session = Depends(get_db),
):
    user = session.get(OpsUser, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    temporary_password = generate_temporary_password()
    user.password_hash = hash_password(temporary_password)
    user.must_change_password = True
    revoke_user_sessions(session, user.id)
    record_auth_event(
        session,
        event_type="password_reset",
        success=True,
        user_id=admin.id,
        details={"target_user_id": user.id},
    )
    session.commit()
    return {"temporary_password": temporary_password}
