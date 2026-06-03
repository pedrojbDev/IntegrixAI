import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


def production_settings(**overrides):
    values = {
        "_env_file": None,
        "environment": "production",
        "database_url": "postgresql+psycopg://app:secret@db.prod.internal:5432/integrix",
        "db_enabled": True,
        "data_mode": "external_api",
        "tenant_map": {"+5511999999999": "tenant_a"},
        "webhook_secret": "secret",
        "ops_dashboard_token": "ops-token",
        "audit_write_mode": "async",
        "external_api_base_url": "https://api.customer-prod.internal",
        "external_api_auth_type": "basic",
        "external_api_username": "user",
        "external_api_password": "password",
    }
    values.update(overrides)
    return Settings(**values)


class DashboardRouteTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def _client(self, settings: Settings) -> TestClient:
        app.dependency_overrides[get_settings] = lambda: settings
        return TestClient(app, base_url="https://testserver")

    def _patch_spa_dist(self):
        temp_dir = tempfile.TemporaryDirectory()
        root = Path(temp_dir.name)
        assets = root / "assets"
        assets.mkdir()
        (root / "index.html").write_text(
            '<div id="root"></div><script type="module" src="/dashboard/assets/index.js"></script>',
            encoding="utf-8",
        )
        (assets / "index.js").write_text("console.log('spa')", encoding="utf-8")
        return temp_dir, patch("app.api.routes.dashboard._SPA_INDEX_PATH", root / "index.html"), patch(
            "app.api.routes.dashboard._SPA_ASSETS_PATH",
            assets,
        )

    def test_dashboard_serves_spa_shell_without_existing_session(self) -> None:
        settings = Settings(
            _env_file=None,
            ops_dashboard_token="ops-token",
            ops_token_header="x-ops-token",
        )
        client = self._client(settings)
        temp_dir, index_patch, assets_patch = self._patch_spa_dist()
        with temp_dir, index_patch, assets_patch:
            response = client.get("/dashboard")

        self.assertEqual(200, response.status_code)
        self.assertIn("/dashboard/assets/index.js", response.text)

    def test_dashboard_asset_serving_is_scoped_to_assets_dir(self) -> None:
        settings = Settings(_env_file=None, ops_dashboard_token="ops-token")
        client = self._client(settings)
        temp_dir, index_patch, assets_patch = self._patch_spa_dist()
        with temp_dir, index_patch, assets_patch:
            response = client.get("/dashboard/assets/index.js")

        self.assertEqual(200, response.status_code)
        self.assertIn("console.log", response.text)

    def test_dashboard_client_routes_return_spa_shell(self) -> None:
        settings = Settings(_env_file=None, ops_dashboard_token="ops-token")
        client = self._client(settings)
        temp_dir, index_patch, assets_patch = self._patch_spa_dist()
        with temp_dir, index_patch, assets_patch:
            diagnostics = client.get("/dashboard/diagnostics")
            audit = client.get("/dashboard/audit")
            nested = client.get("/dashboard/audit/events/recent")

        self.assertEqual(200, diagnostics.status_code)
        self.assertEqual(200, audit.status_code)
        self.assertEqual(200, nested.status_code)
        self.assertIn("/dashboard/assets/index.js", diagnostics.text)

    def test_dashboard_non_production_query_token_sets_cookie(self) -> None:
        settings = Settings(
            _env_file=None,
            ops_dashboard_token="ops-token",
            ops_token_header="x-ops-token",
        )
        client = self._client(settings)
        temp_dir, index_patch, assets_patch = self._patch_spa_dist()
        with temp_dir, index_patch, assets_patch:
            response = client.get("/dashboard?token=ops-token")

        self.assertEqual(200, response.status_code)
        self.assertIn("integrix_ops_session", response.headers.get("set-cookie", ""))

    def test_dashboard_rejects_query_token_in_production(self) -> None:
        client = self._client(production_settings())
        temp_dir, index_patch, assets_patch = self._patch_spa_dist()
        with temp_dir, index_patch, assets_patch:
            response = client.get("/dashboard?token=ops-token")

        self.assertEqual(401, response.status_code)

    def test_dashboard_header_token_sets_secure_cookie_in_production(self) -> None:
        client = self._client(production_settings())
        temp_dir, index_patch, assets_patch = self._patch_spa_dist()
        with temp_dir, index_patch, assets_patch:
            response = client.get("/dashboard", headers={"x-ops-token": "ops-token"})

        cookie = response.headers.get("set-cookie", "")
        self.assertEqual(200, response.status_code)
        self.assertIn("integrix_ops_session", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=lax", cookie)

    def test_dashboard_shell_ignores_stale_cookie_and_still_loads_login_app(self) -> None:
        client = self._client(production_settings())
        client.cookies.set("integrix_ops_session", "stale-token")
        temp_dir, index_patch, assets_patch = self._patch_spa_dist()
        with temp_dir, index_patch, assets_patch:
            response = client.get("/dashboard")

        self.assertEqual(200, response.status_code)
        self.assertIn("/dashboard/assets/index.js", response.text)

    def test_ops_session_valid_token_sets_cookie(self) -> None:
        client = self._client(Settings(_env_file=None, ops_dashboard_token="ops-token"))

        response = client.post("/ops/session", json={"token": "ops-token"})

        self.assertEqual(204, response.status_code)
        self.assertIn("integrix_ops_session", response.headers.get("set-cookie", ""))

    def test_ops_session_invalid_token_returns_401(self) -> None:
        client = self._client(Settings(_env_file=None, ops_dashboard_token="ops-token"))

        response = client.post("/ops/session", json={"token": "wrong"})

        self.assertEqual(401, response.status_code)

    def test_ops_session_rate_limit_hook_runs_before_token_validation(self) -> None:
        client = self._client(Settings(_env_file=None, ops_dashboard_token="ops-token"))

        with patch(
            "app.api.routes.ops_session.enforce_ops_session_rate_limit",
            side_effect=HTTPException(status_code=429, detail="limited"),
        ):
            response = client.post("/ops/session", json={"token": "wrong"})

        self.assertEqual(429, response.status_code)

    def test_ops_session_status_and_logout(self) -> None:
        client = self._client(Settings(_env_file=None, ops_dashboard_token="ops-token"))

        login = client.post("/ops/session", json={"token": "ops-token"})
        session = client.get("/ops/session")
        logout = client.delete("/ops/session")

        self.assertEqual(204, login.status_code)
        self.assertEqual(200, session.status_code)
        self.assertEqual({"authenticated": True}, session.json())
        self.assertEqual(204, logout.status_code)
        self.assertIn("integrix_ops_session", logout.headers.get("set-cookie", ""))

    def test_dashboard_sets_cookie_for_follow_up_ops_requests_in_production(self) -> None:
        client = self._client(production_settings())
        temp_dir, index_patch, assets_patch = self._patch_spa_dist()
        with temp_dir, index_patch, assets_patch:
            dashboard_response = client.get("/dashboard", headers={"x-ops-token": "ops-token"})
        self.assertEqual(200, dashboard_response.status_code)

        with patch("app.api.routes.ops.get_health", return_value={"health_state": "stable"}):
            response = client.get("/ops/dashboard/health?tenant_id=tenant_a")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"health_state": "stable"}, response.json())

    def test_ops_dashboard_requires_tenant_in_production(self) -> None:
        client = self._client(production_settings())

        response = client.get("/ops/dashboard/overview", headers={"x-ops-token": "ops-token"})

        self.assertEqual(400, response.status_code)
        self.assertEqual({"detail": "tenant_id obrigatorio em producao"}, response.json())

    def test_ops_audit_requires_tenant_in_production(self) -> None:
        client = self._client(production_settings())

        recent = client.get("/ops/audit/recent", headers={"x-ops-token": "ops-token"})
        summary = client.get("/ops/audit/summary", headers={"x-ops-token": "ops-token"})

        self.assertEqual(400, recent.status_code)
        self.assertEqual(400, summary.status_code)

    def test_ops_dashboard_accepts_tenant_in_production(self) -> None:
        client = self._client(production_settings())

        with patch("app.api.routes.ops.get_overview", return_value={"tenant_id": "tenant_a"}):
            response = client.get(
                "/ops/dashboard/overview?tenant_id=tenant_a",
                headers={"x-ops-token": "ops-token"},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual({"tenant_id": "tenant_a"}, response.json())

    def test_ops_health_accepts_tenant_in_production(self) -> None:
        client = self._client(production_settings())

        with patch("app.api.routes.ops.get_health", return_value={"health_state": "stable"}):
            response = client.get(
                "/ops/dashboard/health?tenant_id=tenant_a",
                headers={"x-ops-token": "ops-token"},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual({"health_state": "stable"}, response.json())

    def test_ops_resilience_accepts_tenant_in_production(self) -> None:
        client = self._client(production_settings())

        with patch("app.api.routes.ops.get_resilience", return_value={"summary": {"idempotency_hits": 1}}):
            response = client.get(
                "/ops/dashboard/resilience?tenant_id=tenant_a",
                headers={"x-ops-token": "ops-token"},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual({"summary": {"idempotency_hits": 1}}, response.json())

    def test_ops_dashboard_allows_global_query_when_enabled(self) -> None:
        client = self._client(production_settings(ops_allow_global_queries=True))

        with patch("app.api.routes.ops.get_overview", return_value={"global": True}):
            response = client.get("/ops/dashboard/overview", headers={"x-ops-token": "ops-token"})

        self.assertEqual(200, response.status_code)
        self.assertEqual({"global": True}, response.json())


if __name__ == "__main__":
    unittest.main()
