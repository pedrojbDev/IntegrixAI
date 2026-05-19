from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from ...config import Settings, get_settings
from ...core.security.ops import (
    OPS_SESSION_COOKIE_NAME,
    check_ops_token,
    enforce_ops_session_rate_limit,
    require_ops_token,
    session_cookie_settings,
)

router = APIRouter(prefix="/ops", tags=["ops-session"])


class OpsSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1)


@router.post("/session", status_code=status.HTTP_204_NO_CONTENT)
async def create_ops_session(
    payload: OpsSessionRequest,
    response: Response,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    enforce_ops_session_rate_limit(request)
    check_ops_token(payload.token, settings)
    response.set_cookie(
        OPS_SESSION_COOKIE_NAME,
        payload.token,
        **session_cookie_settings(settings),
    )


@router.get("/session")
async def get_ops_session(_: str = Depends(require_ops_token)):
    return {"authenticated": True}


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ops_session(response: Response, settings: Settings = Depends(get_settings)):
    response.delete_cookie(
        OPS_SESSION_COOKIE_NAME,
        secure=settings.is_production,
        samesite="lax",
    )
