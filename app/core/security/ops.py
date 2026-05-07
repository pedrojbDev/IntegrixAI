import hmac

from fastapi import Depends, HTTPException, Request, status

from ...config import Settings, get_settings

OPS_SESSION_COOKIE_NAME = "integrix_ops_session"


def _check_ops_token(provided: str | None, settings: Settings) -> None:
    if not settings.ops_dashboard_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPS_DASHBOARD_TOKEN not configured",
        )

    if not provided or not hmac.compare_digest(provided, settings.ops_dashboard_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ops token")


def require_ops_token(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str:
    header_name = settings.ops_token_header
    provided = request.headers.get(header_name)
    if not provided:
        provided = request.cookies.get(OPS_SESSION_COOKIE_NAME)
    _check_ops_token(provided, settings)
    return provided or ""


def require_ops_token_with_query(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str:
    header_name = settings.ops_token_header
    provided = request.headers.get(header_name)
    if not provided:
        provided = request.cookies.get(OPS_SESSION_COOKIE_NAME)
    if not provided and not settings.is_production:
        provided = request.query_params.get("token")
    _check_ops_token(provided, settings)
    return provided or ""
