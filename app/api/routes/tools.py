from fastapi import APIRouter, Body, Depends, Request

from ...config import Settings, get_settings
from ...core.tools.dispatcher import ToolDispatcher
from ...tenants.pbsaude.tool_handlers import register_pbsaude_handlers

router = APIRouter()
register_pbsaude_handlers()


@router.post("/tools")
async def dispatch_tools(
    http_request: Request,
    payload: dict = Body(...),
    settings: Settings = Depends(get_settings),
):
    """
    Entry point for Vapi tool-calls (message.type='tool-calls') returning always HTTP 200 with results array.
    """
    dispatcher = ToolDispatcher(settings)
    return await dispatcher.dispatch(http_request, payload)
