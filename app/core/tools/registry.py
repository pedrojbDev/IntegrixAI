from __future__ import annotations

from typing import Awaitable, Callable

from ...config import Settings
from ...utils.enums import CallFinalState

ToolHandler = Callable[[dict, Settings, str, str], Awaitable[tuple[dict, CallFinalState]]]


class TenantToolRegistry:
    """Map implementation keys and tool names to async handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, dict[str, ToolHandler]] = {}

    def register(self, implementation_key: str, tool_name: str, handler: ToolHandler) -> None:
        self._handlers.setdefault(implementation_key, {})[tool_name] = handler

    def get_handler(self, implementation_key: str, tool_name: str) -> ToolHandler | None:
        return self._handlers.get(implementation_key, {}).get(tool_name)

    def has_handler(self, implementation_key: str, tool_name: str) -> bool:
        return self.get_handler(implementation_key, tool_name) is not None


tool_registry = TenantToolRegistry()
