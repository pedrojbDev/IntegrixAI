import hmac
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from time import monotonic

from fastapi import Depends, HTTPException, Request, status

from ...config import Settings, get_settings

OPS_SESSION_COOKIE_NAME = "integrix_ops_session"
OPS_SESSION_MAX_AGE_SECONDS = 3600
_SESSION_RATE_LIMIT_WINDOW_SECONDS = 60
_SESSION_RATE_LIMIT_MAX_ATTEMPTS = 10
_session_attempts: dict[str, deque[float]] = defaultdict(deque)


def _check_ops_token(provided: str | None, settings: Settings) -> None:
    if not settings.ops_dashboard_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPS_DASHBOARD_TOKEN not configured",
        )

    if not provided or not hmac.compare_digest(provided, settings.ops_dashboard_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ops token")


def check_ops_token(provided: str | None, settings: Settings) -> None:
    _check_ops_token(provided, settings)


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_ops_session_rate_limit(request: Request) -> None:
    """Minimal local limiter for the SPA login endpoint.

    TODO: replace with shared rate limiting if the ops dashboard is exposed publicly
    behind a proxy or outside the private operations network.
    """

    now = monotonic()
    key = _client_ip(request)
    attempts = _session_attempts[key]
    while attempts and now - attempts[0] > _SESSION_RATE_LIMIT_WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= _SESSION_RATE_LIMIT_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many session attempts",
        )
    attempts.append(now)


def session_cookie_settings(settings: Settings) -> dict[str, object]:
    return {
        "httponly": True,
        "secure": settings.is_production,
        "samesite": "lax",
        "max_age": OPS_SESSION_MAX_AGE_SECONDS,
        "expires": datetime.now(timezone.utc) + timedelta(seconds=OPS_SESSION_MAX_AGE_SECONDS),
    }


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
