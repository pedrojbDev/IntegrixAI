import unittest

from app.api.routes import router as legacy_tools_router
from app.api.routes.tools import router as tools_router
from app.api.security import require_ops_token
from app.core.security.ops import require_ops_token as core_require_ops_token
from app.core.tools.contracts import ToolError as CoreToolError
from app.core.tools.dispatcher import ToolDispatcher as CoreToolDispatcher
from app.schemas.tools import AuthenticateRequest, ToolError, VapiMessage
from app.services.tool_dispatcher import ToolDispatcher
from app.services.tenant import resolve_tenant_details


class ShimTests(unittest.TestCase):
    def test_legacy_routes_import_resolves_to_package_router(self) -> None:
        self.assertIs(legacy_tools_router, tools_router)

    def test_tool_dispatcher_shim_reexports_core_dispatcher(self) -> None:
        self.assertIs(ToolDispatcher, CoreToolDispatcher)

    def test_security_shim_reexports_core_dependency(self) -> None:
        self.assertIs(require_ops_token, core_require_ops_token)

    def test_schemas_shim_exposes_shared_and_pbsaude_contracts(self) -> None:
        self.assertIs(ToolError, CoreToolError)
        self.assertEqual("AuthenticateRequest", AuthenticateRequest.__name__)
        self.assertEqual("VapiMessage", VapiMessage.__name__)

    def test_tenant_shim_exposes_resolver(self) -> None:
        self.assertTrue(callable(resolve_tenant_details))


if __name__ == "__main__":
    unittest.main()
