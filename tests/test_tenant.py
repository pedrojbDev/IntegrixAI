import unittest

from app.config import Settings
from app.core.tenant.resolver import should_reject_tenant_resolution
from app.platform.services.tenant_config_service import TenantConfigService
from app.services.tenant import resolve_tenant, resolve_tenant_details


def production_settings(**overrides):
    values = {
        "_env_file": None,
        "environment": "production",
        "database_url": "postgresql+psycopg://app:secret@db.prod.internal:5432/integrix",
        "db_enabled": True,
        "data_mode": "external_api",
        "default_tenant": "demo",
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


class TenantResolutionTests(unittest.TestCase):
    def test_resolve_tenant_details_prefers_did_map(self) -> None:
        settings = Settings(
            _env_file=None,
            default_tenant="demo",
            tenant_map={"+5511999999999": "tenant_demo"},
        )

        resolution = resolve_tenant_details("+5511999999999", settings)

        self.assertEqual("tenant_demo", resolution.tenant_id)
        self.assertEqual("did_map", resolution.source)
        self.assertFalse(resolution.used_fallback)

    def test_resolve_tenant_details_marks_default_fallback(self) -> None:
        settings = Settings(_env_file=None, default_tenant="demo", tenant_map={})

        resolution = resolve_tenant_details("+5511888888888", settings)

        self.assertEqual("demo", resolution.tenant_id)
        self.assertEqual("default_tenant", resolution.source)
        self.assertTrue(resolution.used_fallback)
        self.assertFalse(should_reject_tenant_resolution(resolution, settings))

    def test_production_rejects_default_tenant_fallback(self) -> None:
        settings = production_settings()

        resolution = resolve_tenant_details("+5511888888888", settings)

        self.assertEqual("demo", resolution.tenant_id)
        self.assertEqual("default_tenant", resolution.source)
        self.assertTrue(should_reject_tenant_resolution(resolution, settings))

    def test_production_rejects_missing_to_number_fallback(self) -> None:
        settings = production_settings()

        resolution = resolve_tenant_details(None, settings)

        self.assertEqual("demo", resolution.tenant_id)
        self.assertEqual("missing_to_number", resolution.source)
        self.assertTrue(should_reject_tenant_resolution(resolution, settings))

    def test_resolve_tenant_details_uses_assistant_map_when_to_number_is_missing(self) -> None:
        settings = production_settings(
            tenant_map={},
            tenant_assistant_map={"assistant_123": "tenant_demo"},
        )

        resolution = resolve_tenant_details(None, settings, assistant_id="assistant_123")

        self.assertEqual("tenant_demo", resolution.tenant_id)
        self.assertEqual("assistant_map", resolution.source)
        self.assertFalse(resolution.used_fallback)
        self.assertFalse(should_reject_tenant_resolution(resolution, settings))

    def test_resolve_tenant_details_uses_phone_number_map_when_to_number_is_missing(self) -> None:
        settings = production_settings(
            tenant_map={},
            tenant_phone_number_map={"phone_number_123": "tenant_demo"},
        )

        resolution = resolve_tenant_details(None, settings, phone_number_id="phone_number_123")

        self.assertEqual("tenant_demo", resolution.tenant_id)
        self.assertEqual("phone_number_id_map", resolution.source)
        self.assertFalse(resolution.used_fallback)
        self.assertFalse(should_reject_tenant_resolution(resolution, settings))

    def test_resolve_tenant_keeps_legacy_contract(self) -> None:
        settings = Settings(_env_file=None, default_tenant="demo", tenant_map={})

        self.assertEqual("demo", resolve_tenant(None, settings))

    def test_tenant_config_service_defaults_all_tenants_to_pbsaude(self) -> None:
        settings = Settings(_env_file=None)

        service = TenantConfigService(settings)

        self.assertEqual("pbsaude", service.get_implementation_key("tenant_a"))
        self.assertEqual("pbsaude", service.get_implementation_key("tenant_b"))

    def test_tenant_config_service_allows_override_map(self) -> None:
        settings = Settings(
            _env_file=None,
            tenant_implementation_map={"tenant_b": "custom_impl"},
        )

        service = TenantConfigService(settings)

        self.assertEqual("pbsaude", service.get_implementation_key("tenant_a"))
        self.assertEqual("custom_impl", service.get_implementation_key("tenant_b"))


if __name__ == "__main__":
    unittest.main()
