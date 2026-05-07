from functools import lru_cache
import json
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ...config import Settings, get_settings
from ...core.security.ops import OPS_SESSION_COOKIE_NAME, require_ops_token_with_query

router = APIRouter(tags=["dashboard"])

_DASHBOARD_HTML_PATH = Path(__file__).resolve().parents[2] / "static" / "dashboard" / "index.html"


@lru_cache(maxsize=1)
def _load_dashboard_shell() -> str:
    return _DASHBOARD_HTML_PATH.read_text(encoding="utf-8")


def _build_bootstrap(settings: Settings) -> str:
    payload = {
        "token": "" if settings.is_production else settings.ops_dashboard_token or "",
        "headerName": settings.ops_token_header,
        "refreshIntervalMs": 45_000,
    }
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    token: str = Depends(require_ops_token_with_query),
    settings: Settings = Depends(get_settings),
):
    page = _load_dashboard_shell().replace("__DASHBOARD_BOOTSTRAP__", _build_bootstrap(settings))
    response = HTMLResponse(page)
    if settings.is_production:
        response.set_cookie(
            OPS_SESSION_COOKIE_NAME,
            token,
            httponly=True,
            samesite="lax",
            max_age=3600,
        )
    return response
