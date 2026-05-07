import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


def production_settings(**overrides):
    values = {
        "_env_file": None,
        "environment": "production",
        "database_url": "postgresql+psycopg://app:secret@db.example.com:5432/integrix",
        "db_enabled": True,
        "data_mode": "external_api",
        "tenant_map": {"+5511999999999": "tenant_a"},
        "webhook_secret": "secret",
        "ops_dashboard_token": "ops-token",
        "audit_write_mode": "async",
        "external_api_base_url": "https://customer-api.example",
        "external_api_auth_type": "basic",
        "external_api_username": "user",
        "external_api_password": "password",
    }
    values.update(overrides)
    return Settings(**values)


class DashboardRouteTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_dashboard_accepts_query_token_and_uses_external_assets(self) -> None:
        settings = Settings(
            _env_file=None,
            ops_dashboard_token="ops-token",
            ops_token_header="x-ops-token",
        )
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        response = client.get("/dashboard?token=ops-token")

        self.assertEqual(200, response.status_code)
        self.assertIn('/static/dashboard/dashboard.css', response.text)
        self.assertIn('/static/dashboard/dashboard.js', response.text)
        self.assertIn('"headerName": "x-ops-token"', response.text)
        self.assertIn('"token": "ops-token"', response.text)
        self.assertNotIn("<style>", response.text)

    def test_dashboard_accepts_header_token(self) -> None:
        settings = Settings(
            _env_file=None,
            ops_dashboard_token="ops-token",
            ops_token_header="x-ops-token",
        )
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        response = client.get("/dashboard", headers={"x-ops-token": "ops-token"})

        self.assertEqual(200, response.status_code)
        self.assertIn("dashboard-bootstrap", response.text)

    def test_dashboard_rejects_query_token_in_production(self) -> None:
        settings = production_settings()
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        response = client.get("/dashboard?token=ops-token")

        self.assertEqual(401, response.status_code)

    def test_dashboard_omits_bootstrap_token_in_production(self) -> None:
        settings = production_settings()
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        response = client.get("/dashboard", headers={"x-ops-token": "ops-token"})

        self.assertEqual(200, response.status_code)
        self.assertIn('"headerName": "x-ops-token"', response.text)
        self.assertIn('"token": ""', response.text)
        self.assertNotIn('"token": "ops-token"', response.text)

    def test_ops_dashboard_requires_tenant_in_production(self) -> None:
        settings = production_settings()
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        response = client.get("/ops/dashboard/overview", headers={"x-ops-token": "ops-token"})

        self.assertEqual(400, response.status_code)
        self.assertEqual({"detail": "tenant_id obrigatorio em producao"}, response.json())

    def test_ops_audit_requires_tenant_in_production(self) -> None:
        settings = production_settings()
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        recent = client.get("/ops/audit/recent", headers={"x-ops-token": "ops-token"})
        summary = client.get("/ops/audit/summary", headers={"x-ops-token": "ops-token"})

        self.assertEqual(400, recent.status_code)
        self.assertEqual(400, summary.status_code)

    def test_ops_dashboard_accepts_tenant_in_production(self) -> None:
        settings = production_settings()
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        with patch("app.api.routes.ops.get_overview", return_value={"tenant_id": "tenant_a"}):
            response = client.get(
                "/ops/dashboard/overview?tenant_id=tenant_a",
                headers={"x-ops-token": "ops-token"},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual({"tenant_id": "tenant_a"}, response.json())

    def test_ops_dashboard_allows_global_query_when_enabled(self) -> None:
        settings = production_settings(ops_allow_global_queries=True)
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)

        with patch("app.api.routes.ops.get_overview", return_value={"global": True}):
            response = client.get("/ops/dashboard/overview", headers={"x-ops-token": "ops-token"})

        self.assertEqual(200, response.status_code)
        self.assertEqual({"global": True}, response.json())


if __name__ == "__main__":
    unittest.main()
