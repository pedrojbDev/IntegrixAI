import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.core.security.ops import hash_password
from app.db import Base, get_db
from app.main import app
from app.models.ops_auth import OpsUser, OpsUserTenant


def production_settings(**overrides):
    values = {
        "_env_file": None,
        "environment": "production",
        "database_url": "postgresql+psycopg://app:secret@db.prod.internal:5432/integrix",
        "db_enabled": True,
        "data_mode": "external_api",
        "tenant_map": {"+5511999999999": "tenant_a"},
        "webhook_secret": "secret",
        "ops_dashboard_token": "ops-bootstrap-token",
        "audit_write_mode": "async",
        "external_api_base_url": "https://api.customer-prod.internal",
        "external_api_auth_type": "basic",
        "external_api_username": "user",
        "external_api_password": "password",
    }
    values.update(overrides)
    return Settings(**values)


class DashboardRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_local = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.route_session_patch = patch("app.api.routes.ops.SessionLocal", self.session_local)
        self.route_session_patch.start()

    def tearDown(self) -> None:
        self.route_session_patch.stop()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _client(self, settings: Settings | None = None) -> TestClient:
        selected_settings = settings or production_settings()
        app.dependency_overrides[get_settings] = lambda: selected_settings

        def override_db():
            session = self.session_local()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
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

    def _bootstrap(self, client: TestClient, email: str = "admin@example.com") -> dict:
        response = client.post(
            "/ops/bootstrap",
            json={
                "email": email,
                "password": "long-initial-password",
                "token": "ops-bootstrap-token",
            },
        )
        self.assertEqual(201, response.status_code, response.text)
        return response.json()

    @staticmethod
    def _csrf(client: TestClient) -> dict[str, str]:
        return {
            "x-csrf-token": client.cookies.get("integrix_ops_csrf"),
            "origin": "https://testserver",
        }

    def _create_tenant_user(
        self,
        *,
        email: str = "client@example.com",
        tenants: tuple[str, ...] = ("tenant_a",),
        password: str = "client-password-123",
        must_change_password: bool = False,
    ) -> None:
        with self.session_local() as session:
            user = OpsUser(
                email=email,
                password_hash=hash_password(password),
                role="tenant_user",
                is_active=True,
                must_change_password=must_change_password,
            )
            session.add(user)
            session.flush()
            session.add_all(
                OpsUserTenant(user_id=user.id, tenant_id=tenant_id)
                for tenant_id in tenants
            )
            session.commit()

    def test_dashboard_serves_spa_without_accepting_token_query_or_header(self) -> None:
        client = self._client()
        temp_dir, index_patch, assets_patch = self._patch_spa_dist()
        with temp_dir, index_patch, assets_patch:
            response = client.get(
                "/dashboard?token=ops-bootstrap-token",
                headers={"x-ops-token": "ops-bootstrap-token"},
            )

        self.assertEqual(200, response.status_code)
        self.assertIn("/dashboard/assets/index.js", response.text)
        self.assertNotIn("integrix_ops_session", response.headers.get("set-cookie", ""))

    def test_dashboard_assets_and_client_routes_use_spa(self) -> None:
        client = self._client()
        temp_dir, index_patch, assets_patch = self._patch_spa_dist()
        with temp_dir, index_patch, assets_patch:
            asset = client.get("/dashboard/assets/index.js")
            diagnostics = client.get("/dashboard/diagnostics")
            users = client.get("/dashboard/admin/users")

        self.assertEqual(200, asset.status_code)
        self.assertEqual(200, diagnostics.status_code)
        self.assertEqual(200, users.status_code)

    def test_bootstrap_is_single_use_and_token_never_authenticates_dashboard(self) -> None:
        client = self._client()
        principal = self._bootstrap(client)["principal"]

        duplicate = client.post(
            "/ops/bootstrap",
            json={
                "email": "other@example.com",
                "password": "long-initial-password",
                "token": "ops-bootstrap-token",
            },
        )
        client.cookies.clear()
        token_only = client.get(
            "/ops/session",
            headers={"x-ops-token": "ops-bootstrap-token"},
        )

        self.assertEqual("platform_admin", principal["role"])
        self.assertFalse(principal["must_change_password"])
        self.assertEqual(409, duplicate.status_code)
        self.assertEqual(401, token_only.status_code)

    def test_email_password_session_and_csrf_logout(self) -> None:
        client = self._client()
        self._bootstrap(client)
        client.cookies.clear()

        login = client.post(
            "/ops/session",
            json={"email": "ADMIN@example.com", "password": "long-initial-password"},
        )
        session = client.get("/ops/session")
        rejected_logout = client.delete("/ops/session")
        logout = client.delete("/ops/session", headers=self._csrf(client))
        revoked = client.get("/ops/session")

        self.assertEqual(200, login.status_code)
        self.assertEqual("admin@example.com", session.json()["principal"]["email"])
        self.assertIn("HttpOnly", login.headers.get("set-cookie", ""))
        self.assertIn("Secure", login.headers.get("set-cookie", ""))
        self.assertEqual(403, rejected_logout.status_code)
        self.assertEqual(204, logout.status_code)
        self.assertEqual(401, revoked.status_code)

    def test_login_rate_limit_is_persisted_in_database(self) -> None:
        client = self._client(production_settings(ops_login_max_attempts=3))
        self._bootstrap(client)
        client.cookies.clear()

        first = client.post(
            "/ops/session",
            json={"email": "admin@example.com", "password": "incorrect-password"},
        )
        second = client.post(
            "/ops/session",
            json={"email": "admin@example.com", "password": "incorrect-password"},
        )
        third = client.post(
            "/ops/session",
            json={"email": "admin@example.com", "password": "incorrect-password"},
        )
        blocked = client.post(
            "/ops/session",
            json={"email": "admin@example.com", "password": "long-initial-password"},
        )

        self.assertEqual(401, first.status_code)
        self.assertEqual(401, second.status_code)
        self.assertEqual(401, third.status_code)
        self.assertEqual(429, blocked.status_code)

    def test_tenant_user_is_closed_to_memberships_and_cross_tenant_access(self) -> None:
        self._create_tenant_user(tenants=("tenant_a", "tenant_b"))
        client = self._client()
        login = client.post(
            "/ops/session",
            json={"email": "client@example.com", "password": "client-password-123"},
        )
        with patch("app.api.routes.ops.get_overview", return_value={"tenant_id": "tenant_b"}):
            allowed = client.get("/ops/dashboard/overview?tenant_id=tenant_b")
            missing = client.get("/ops/dashboard/overview")
            denied = client.get("/ops/dashboard/overview?tenant_id=tenant_c")
        sync = client.post("/ops/costs/sync", headers=self._csrf(client))

        self.assertEqual(200, login.status_code)
        self.assertEqual(200, allowed.status_code)
        self.assertEqual(400, missing.status_code)
        self.assertEqual(403, denied.status_code)
        self.assertEqual(403, sync.status_code)

    def test_single_tenant_user_gets_membership_when_filter_is_absent(self) -> None:
        self._create_tenant_user()
        client = self._client()
        client.post(
            "/ops/session",
            json={"email": "client@example.com", "password": "client-password-123"},
        )
        with patch("app.api.routes.ops.get_health", return_value={"health_state": "stable"}) as service:
            response = client.get("/ops/dashboard/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual("tenant_a", service.call_args.kwargs["tenant_id"])

    def test_admin_global_scope_requires_explicit_flag(self) -> None:
        client = self._client()
        self._bootstrap(client)
        required = client.get("/ops/dashboard/overview")
        self.assertEqual(400, required.status_code)

        app.dependency_overrides[get_settings] = lambda: production_settings(
            ops_allow_global_queries=True
        )
        with patch("app.api.routes.ops.get_overview", return_value={"global": True}):
            allowed = client.get("/ops/dashboard/overview")
        self.assertEqual(200, allowed.status_code)

    def test_admin_crud_returns_temporary_password_once(self) -> None:
        client = self._client()
        self._bootstrap(client)

        created = client.post(
            "/ops/admin/users",
            headers=self._csrf(client),
            json={
                "email": "customer@example.com",
                "role": "tenant_user",
                "tenant_ids": ["tenant_a", "tenant_b"],
            },
        )
        users = client.get("/ops/admin/users")
        user_id = created.json()["user"]["id"]
        reset = client.post(
            f"/ops/admin/users/{user_id}/reset-password",
            headers=self._csrf(client),
        )

        self.assertEqual(201, created.status_code, created.text)
        self.assertTrue(created.json()["temporary_password"])
        self.assertEqual(2, len(users.json()))
        self.assertTrue(reset.json()["temporary_password"])
        self.assertNotEqual(
            created.json()["temporary_password"],
            reset.json()["temporary_password"],
        )

    def test_temporary_password_must_be_changed_and_revokes_session(self) -> None:
        self._create_tenant_user(must_change_password=True)
        client = self._client()
        client.post(
            "/ops/session",
            json={"email": "client@example.com", "password": "client-password-123"},
        )

        dashboard = client.get("/ops/dashboard/overview?tenant_id=tenant_a")
        changed = client.post(
            "/ops/session/password",
            headers=self._csrf(client),
            json={
                "current_password": "client-password-123",
                "new_password": "new-client-password-456",
            },
        )
        revoked = client.get("/ops/session")

        self.assertEqual(403, dashboard.status_code)
        self.assertEqual(204, changed.status_code)
        self.assertEqual(401, revoked.status_code)

    def test_report_is_tenant_scoped_and_audited(self) -> None:
        client = self._client()
        self._bootstrap(client)
        with patch(
            "app.api.routes.ops.build_operational_report_pdf",
            return_value=b"%PDF-demo",
        ) as report:
            response = client.get(
                "/ops/reports/operational.pdf?period_days=30&tenant_id=tenant_a"
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("application/pdf", response.headers.get("content-type"))
        self.assertEqual("tenant_a", report.call_args.kwargs["tenant_id"])


if __name__ == "__main__":
    unittest.main()
