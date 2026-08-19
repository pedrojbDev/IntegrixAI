import unittest
from unittest.mock import AsyncMock

from app.core.tools.registry import TenantToolRegistry
from app.tenants.pbsaude.mappings import (
    TOOL_AUTHENTICATE_MEMBER,
    TOOL_GET_AUTHORIZATION_STATUS,
    TOOL_HANDOFF_HUMAN,
    TOOL_SEARCH_PROVIDERS,
)
from app.tenants.pbsaude.tool_handlers import PBSAUDE_IMPLEMENTATION_KEY, register_pbsaude_handlers


class TenantToolRegistryTests(unittest.TestCase):
    def test_registry_returns_handler_by_implementation_and_tool_name(self) -> None:
        registry = TenantToolRegistry()
        handler = AsyncMock()

        registry.register("pbsaude", "handoff_human", handler)

        self.assertTrue(registry.has_handler("pbsaude", "handoff_human"))
        self.assertIs(handler, registry.get_handler("pbsaude", "handoff_human"))
        self.assertIsNone(registry.get_handler("other_impl", "handoff_human"))

    def test_pbsaude_registers_only_active_vapi_tools(self) -> None:
        registry = TenantToolRegistry()

        register_pbsaude_handlers(registry)

        self.assertTrue(registry.has_handler(PBSAUDE_IMPLEMENTATION_KEY, TOOL_SEARCH_PROVIDERS))
        self.assertTrue(registry.has_handler(PBSAUDE_IMPLEMENTATION_KEY, TOOL_HANDOFF_HUMAN))
        self.assertFalse(registry.has_handler(PBSAUDE_IMPLEMENTATION_KEY, TOOL_AUTHENTICATE_MEMBER))
        self.assertFalse(
            registry.has_handler(PBSAUDE_IMPLEMENTATION_KEY, TOOL_GET_AUTHORIZATION_STATUS)
        )


if __name__ == "__main__":
    unittest.main()
