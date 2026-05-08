from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.routes.dashboard import router as dashboard_router
from .api.routes.health import router as health_router
from .api.routes.ops import router as ops_router
from .api.routes.tools import router as tools_router
from .config import get_settings
from .core.audit.service import stop_audit_worker
from .logging import setup_logging
from .tenants.pbsaude.integration.http_client import close_external_api_client

settings = get_settings()
setup_logging(settings.log_level)

app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")
app.include_router(tools_router)
app.include_router(ops_router)
app.include_router(dashboard_router)
app.include_router(health_router)


@app.on_event("shutdown")
def shutdown_audit_worker() -> None:
    stop_audit_worker()
    close_external_api_client()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
