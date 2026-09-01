from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ...config import Settings, get_settings
from ...core.security.webhook import is_webhook_authorized
from ...db import SessionLocal
from ...platform.services.vapi_event_ingestion import VapiEventIngestionService, VapiEventValidationError
from ...schemas.vapi_events import VapiServerEvent


router = APIRouter(tags=["vapi"])


@router.post("/vapi/events", status_code=status.HTTP_204_NO_CONTENT)
async def ingest_vapi_event(
    http_request: Request,
    event: VapiServerEvent,
    settings: Settings = Depends(get_settings),
) -> Response:
    if not is_webhook_authorized(http_request, settings):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized webhook")

    session = SessionLocal()
    try:
        VapiEventIngestionService(settings).ingest(session, event.model_dump())
    except VapiEventValidationError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
