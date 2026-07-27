from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...config import Settings, get_settings
from ...core.security.ops import (
    OpsPrincipal,
    authenticate_user,
    clear_ops_session_cookies,
    create_ops_session,
    hash_password,
    record_auth_event,
    require_csrf,
    require_ops_principal,
    revoke_session,
    revoke_user_sessions,
    user_to_dict,
    verify_password,
)
from ...db import get_db
from ...models.ops_auth import OpsUser
from ...schemas.ops_auth import (
    OpsBootstrapRequest,
    OpsLoginRequest,
    OpsPasswordChangeRequest,
    OpsSessionResponse,
)

router = APIRouter(prefix="/ops", tags=["ops-session"])
BOOTSTRAP_ADVISORY_LOCK_ID = 1_908_244_011


@router.post("/bootstrap", response_model=OpsSessionResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap_ops_admin(
    payload: OpsBootstrapRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db),
):
    if session.get_bind().dialect.name == "postgresql":
        session.execute(select(func.pg_advisory_xact_lock(BOOTSTRAP_ADVISORY_LOCK_ID)))
    existing_admins = int(
        session.execute(
            select(func.count(OpsUser.id)).where(OpsUser.role == "platform_admin")
        ).scalar()
        or 0
    )
    if existing_admins:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bootstrap already completed")
    if not settings.ops_dashboard_token or not hmac.compare_digest(
        payload.token, settings.ops_dashboard_token
    ):
        record_auth_event(session, event_type="bootstrap", success=False)
        session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bootstrap token")
    if session.execute(
        select(OpsUser.id).where(OpsUser.email == payload.email)
    ).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    user = OpsUser(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role="platform_admin",
        is_active=True,
        must_change_password=False,
    )
    session.add(user)
    session.flush()
    record_auth_event(session, event_type="bootstrap", success=True, user_id=user.id)
    session.commit()
    principal = create_ops_session(session, response, user, settings)
    return {"authenticated": True, "principal": user_to_dict(user) | {"tenant_ids": list(principal.tenant_ids)}}


@router.post("/session", response_model=OpsSessionResponse)
async def login_ops_session(
    payload: OpsLoginRequest,
    response: Response,
    request: Request,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db),
):
    user = authenticate_user(session, request, payload.email, payload.password, settings)
    create_ops_session(session, response, user, settings)
    return {"authenticated": True, "principal": user_to_dict(user)}


@router.get("/session", response_model=OpsSessionResponse)
async def get_ops_session(principal: OpsPrincipal = Depends(require_ops_principal)):
    return {
        "authenticated": True,
        "principal": {
            "id": principal.id,
            "email": principal.email,
            "role": principal.role,
            "tenant_ids": list(principal.tenant_ids),
            "must_change_password": principal.must_change_password,
        },
    }


@router.post("/session/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_ops_password(
    payload: OpsPasswordChangeRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
    principal: OpsPrincipal = Depends(require_csrf),
    session: Session = Depends(get_db),
):
    user = session.get(OpsUser, principal.id)
    if user is None or not verify_password(user.password_hash, payload.current_password):
        record_auth_event(
            session,
            event_type="password_changed",
            success=False,
            user_id=principal.id,
        )
        session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password invalid")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    revoke_user_sessions(session, user.id)
    record_auth_event(session, event_type="password_changed", success=True, user_id=user.id)
    session.commit()
    clear_ops_session_cookies(response, settings)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ops_session(
    response: Response,
    settings: Settings = Depends(get_settings),
    principal: OpsPrincipal = Depends(require_csrf),
    session: Session = Depends(get_db),
):
    revoke_session(session, principal)
    record_auth_event(session, event_type="logout", success=True, user_id=principal.id)
    session.commit()
    clear_ops_session_cookies(response, settings)
