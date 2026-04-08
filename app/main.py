from fastapi import FastAPI

from .api.dashboard import router as dashboard_router
from .api.ops import router as ops_router
from .api.routes import router as tools_router
from .config import get_settings
from .logging import setup_logging

settings = get_settings()
setup_logging(settings.log_level)

app = FastAPI(title=settings.app_name)
app.include_router(tools_router)
app.include_router(ops_router)
app.include_router(dashboard_router)


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.environment, "data_mode": settings.data_mode}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
