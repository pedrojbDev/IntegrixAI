from __future__ import annotations

from ...core.tools.registry import TenantToolRegistry, ToolHandler, tool_registry
from ...db import SessionLocal
from ...platform.services.vapi_conversation import register_conversation_policy
from .conversation import capture_pbsaude_conversation
from .mappings import (
    TOOL_AUTHENTICATE_MEMBER,
    TOOL_GET_AUTHORIZATION_STATUS,
    TOOL_HANDOFF_HUMAN,
    TOOL_SEARCH_PROVIDERS,
)
from .policies import is_tool_enabled
from .workflows.authenticate_member import authenticate_member
from .workflows.get_authorization_status import get_authorization_status
from .workflows.handoff_human import handoff_human
from .workflows.search_providers import search_providers

PBSAUDE_IMPLEMENTATION_KEY = "pbsaude"

PBSAUDE_TOOL_HANDLERS: dict[str, ToolHandler] = {
    TOOL_AUTHENTICATE_MEMBER: authenticate_member,
    TOOL_GET_AUTHORIZATION_STATUS: get_authorization_status,
    TOOL_SEARCH_PROVIDERS: search_providers,
    TOOL_HANDOFF_HUMAN: handoff_human,
}


def prepare_pbsaude_request(payload, settings, call_id, tenant_id) -> None:
    if not settings.vapi_slot_guard_enabled:
        return
    with SessionLocal() as session:
        capture_pbsaude_conversation(session, settings, tenant_id, call_id, payload.get("message", {}))
        session.commit()


def register_pbsaude_handlers(registry: TenantToolRegistry | None = None) -> TenantToolRegistry:
    register_conversation_policy(PBSAUDE_IMPLEMENTATION_KEY, capture_pbsaude_conversation)
    active_registry = registry or tool_registry
    active_registry.register_request_preparer(PBSAUDE_IMPLEMENTATION_KEY, prepare_pbsaude_request)
    active_registry.set_batch_limit(PBSAUDE_IMPLEMENTATION_KEY, TOOL_SEARCH_PROVIDERS, 1)
    for tool_name, handler in PBSAUDE_TOOL_HANDLERS.items():
        if not is_tool_enabled(tool_name):
            continue
        active_registry.register(PBSAUDE_IMPLEMENTATION_KEY, tool_name, handler)
    return active_registry
