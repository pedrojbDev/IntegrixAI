from functools import lru_cache
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse

from ...config import Settings, get_settings
from ...core.security.ops import (
    OPS_SESSION_COOKIE_NAME,
    check_ops_token,
    session_cookie_settings,
)

router = APIRouter(tags=["dashboard"])

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_FRONTEND_DIST_PATH = _PROJECT_ROOT / "frontend" / "dist"
_SPA_INDEX_PATH = _FRONTEND_DIST_PATH / "index.html"
_SPA_ASSETS_PATH = _FRONTEND_DIST_PATH / "assets"
_LEGACY_DASHBOARD_HTML_PATH = Path(__file__).resolve().parents[2] / "static" / "dashboard" / "index.html"


@lru_cache(maxsize=1)
def _load_legacy_dashboard_shell() -> str:
    return _LEGACY_DASHBOARD_HTML_PATH.read_text(encoding="utf-8")


def _build_legacy_bootstrap(settings: Settings) -> str:
    payload = {
        "token": "" if settings.is_production else settings.ops_dashboard_token or "",
        "headerName": settings.ops_token_header,
        "refreshIntervalMs": 45_000,
    }
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _spa_available() -> bool:
    return _SPA_INDEX_PATH.is_file()


def _serve_legacy_dashboard(settings: Settings) -> HTMLResponse:
    page = _load_legacy_dashboard_shell().replace(
        "__DASHBOARD_BOOTSTRAP__",
        _build_legacy_bootstrap(settings),
    )
    return HTMLResponse(page)


def _set_ops_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        OPS_SESSION_COOKIE_NAME,
        token,
        **session_cookie_settings(settings),
    )


def _dashboard_bootstrap_token(request: Request, settings: Settings) -> str:
    if settings.is_production and request.query_params.get("token"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ops token")

    header_token = request.headers.get(settings.ops_token_header)
    query_token = None if settings.is_production else request.query_params.get("token")
    provided = header_token or query_token
    if not provided:
        return ""
    check_ops_token(provided, settings)
    return provided


def _serve_spa_index(token: str, settings: Settings) -> FileResponse | HTMLResponse:
    if not _spa_available():
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dashboard frontend build not found. Run npm run build in frontend/.",
            )
        response = _serve_legacy_dashboard(settings)
    else:
        response = FileResponse(_SPA_INDEX_PATH)

    if token:
        _set_ops_session_cookie(response, token, settings)
    return response


@router.get("/dashboard/assets/{asset_path:path}")
async def dashboard_asset(asset_path: str):
    asset = (_SPA_ASSETS_PATH / asset_path).resolve()
    assets_root = _SPA_ASSETS_PATH.resolve()
    try:
        asset.relative_to(assets_root)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    if not asset.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return FileResponse(asset)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    settings: Settings = Depends(get_settings),
):
    token = _dashboard_bootstrap_token(request, settings)
    return _serve_spa_index(token, settings)


@router.get("/dashboard/{client_path:path}", response_class=HTMLResponse)
async def dashboard_spa_fallback(
    client_path: str,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    if client_path.startswith("assets/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    token = _dashboard_bootstrap_token(request, settings)
    return _serve_spa_index(token, settings)
