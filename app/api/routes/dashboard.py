from functools import lru_cache
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse

from ...config import Settings, get_settings

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
        "token": "",
        "headerName": "",
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


def _serve_spa_index(settings: Settings) -> FileResponse | HTMLResponse:
    if not _spa_available():
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dashboard frontend build not found. Run npm run build in frontend/.",
            )
        response = _serve_legacy_dashboard(settings)
    else:
        response = FileResponse(_SPA_INDEX_PATH)

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
    settings: Settings = Depends(get_settings),
):
    return _serve_spa_index(settings)


@router.get("/dashboard/{client_path:path}", response_class=HTMLResponse)
async def dashboard_spa_fallback(
    client_path: str,
    settings: Settings = Depends(get_settings),
):
    if client_path.startswith("assets/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return _serve_spa_index(settings)
