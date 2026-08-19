from __future__ import annotations

from ...core.tools.registry import TenantToolRegistry, ToolHandler, tool_registry
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


def register_pbsaude_handlers(registry: TenantToolRegistry | None = None) -> TenantToolRegistry:
    active_registry = registry or tool_registry
    for tool_name, handler in PBSAUDE_TOOL_HANDLERS.items():
        if not is_tool_enabled(tool_name):
            continue
        active_registry.register(PBSAUDE_IMPLEMENTATION_KEY, tool_name, handler)
    return active_registry
