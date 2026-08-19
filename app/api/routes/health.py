from fastapi import APIRouter, Depends

from ...config import Settings, get_settings

router = APIRouter()


@router.get("/health")
async def health(settings: Settings = Depends(get_settings)):
    return {"status": "ok", "environment": settings.environment, "data_mode": settings.data_mode}
