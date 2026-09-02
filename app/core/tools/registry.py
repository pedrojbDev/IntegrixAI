from __future__ import annotations

from typing import Awaitable, Callable

from ...config import Settings
from ...utils.enums import CallFinalState

ToolHandler = Callable[[dict, Settings, str, str], Awaitable[tuple[dict, CallFinalState]]]


class TenantToolRegistry:
    """Map implementation keys and tool names to async handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, dict[str, ToolHandler]] = {}
        self._preparers: dict[str, Callable] = {}
        self._batch_limits: dict[tuple[str, str], int] = {}

    def register_request_preparer(self, implementation_key: str, preparer: Callable) -> None:
        self._preparers[implementation_key] = preparer

    def prepare_request(self, implementation_key: str, payload: dict, settings: Settings,
                        call_id: str, tenant_id: str) -> None:
        preparer = self._preparers.get(implementation_key)
        if preparer:
            preparer(payload, settings, call_id, tenant_id)

    def set_batch_limit(self, implementation_key: str, tool_name: str, limit: int) -> None:
        self._batch_limits[(implementation_key, tool_name)] = limit

    def batch_limit(self, implementation_key: str, tool_name: str) -> int | None:
        return self._batch_limits.get((implementation_key, tool_name))

    def register(self, implementation_key: str, tool_name: str, handler: ToolHandler) -> None:
        self._handlers.setdefault(implementation_key, {})[tool_name] = handler

    def get_handler(self, implementation_key: str, tool_name: str) -> ToolHandler | None:
        return self._handlers.get(implementation_key, {}).get(tool_name)

    def has_handler(self, implementation_key: str, tool_name: str) -> bool:
        return self.get_handler(implementation_key, tool_name) is not None


tool_registry = TenantToolRegistry()
