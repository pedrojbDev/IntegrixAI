import unittest

from pydantic import ValidationError

from app.config import Settings


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
        "chaos_error_rate": 0.0,
        "chaos_latency_ms": 0,
    }
    values.update(overrides)
    return Settings(**values)


class SettingsTests(unittest.TestCase):
    def test_production_requires_webhook_secret(self) -> None:
        with self.assertRaisesRegex(ValidationError, "WEBHOOK_SECRET"):
            production_settings(webhook_secret=None)

    def test_production_rejects_blank_webhook_secret(self) -> None:
        with self.assertRaisesRegex(ValidationError, "WEBHOOK_SECRET"):
            production_settings(webhook_secret="   ")

    def test_production_accepts_webhook_secret(self) -> None:
        settings = production_settings(environment=" production ", webhook_secret=" secret ")

        self.assertTrue(settings.is_production)
        self.assertEqual("secret", settings.webhook_secret)

    def test_non_production_allows_missing_webhook_secret(self) -> None:
        settings = Settings(_env_file=None, environment="dev", webhook_secret="   ")

        self.assertFalse(settings.is_production)
        self.assertIsNone(settings.webhook_secret)

    def test_production_rejects_mock_mode(self) -> None:
        with self.assertRaisesRegex(ValidationError, "DATA_MODE=external_api"):
            production_settings(data_mode="mock")

    def test_production_requires_db_enabled(self) -> None:
        with self.assertRaisesRegex(ValidationError, "DB_ENABLED=true"):
            production_settings(db_enabled=False)

    def test_production_requires_tenant_map(self) -> None:
        with self.assertRaisesRegex(ValidationError, "TENANT_MAP"):
            production_settings(tenant_map={})

    def test_production_requires_external_api_credentials(self) -> None:
        with self.assertRaisesRegex(ValidationError, "EXTERNAL_API_USERNAME/EXTERNAL_API_PASSWORD"):
            production_settings(external_api_password=None)

    def test_production_rejects_chaos_mode(self) -> None:
        with self.assertRaisesRegex(ValidationError, "CHAOS_ERROR_RATE=0"):
            production_settings(chaos_error_rate=0.25)

    def test_production_rejects_local_database_url(self) -> None:
        with self.assertRaisesRegex(ValidationError, "non-local DATABASE_URL"):
            production_settings(
                database_url="postgresql+psycopg://postgres:postgres@localhost:5432/integrix"
            )

    def test_production_requires_async_audit(self) -> None:
        with self.assertRaisesRegex(ValidationError, "AUDIT_WRITE_MODE=async"):
            production_settings(audit_write_mode="sync")

    def test_db_and_audit_settings_are_clamped(self) -> None:
        settings = Settings(
            _env_file=None,
            db_pool_size=0,
            db_max_overflow=-1,
            db_pool_timeout_seconds=0.1,
            db_pool_recycle_seconds=1,
            audit_queue_max_size=0,
            audit_batch_size=0,
            audit_flush_interval_seconds=0.001,
            call_events_retention_days=0,
            vapi_cost_retention_days=0,
        )

        self.assertEqual(1, settings.db_pool_size)
        self.assertEqual(0, settings.db_max_overflow)
        self.assertEqual(0.5, settings.db_pool_timeout_seconds)
        self.assertEqual(60, settings.db_pool_recycle_seconds)
        self.assertEqual(1, settings.audit_queue_max_size)
        self.assertEqual(1, settings.audit_batch_size)
        self.assertEqual(0.05, settings.audit_flush_interval_seconds)
        self.assertEqual(1, settings.call_events_retention_days)
        self.assertEqual(1, settings.vapi_cost_retention_days)

    def test_external_api_resilience_settings_are_clamped(self) -> None:
        settings = Settings(
            _env_file=None,
            external_api_max_retries=99,
            external_api_retry_backoff_seconds=99,
            external_api_max_connections=0,
            external_api_max_keepalive_connections=-1,
        )

        self.assertEqual(3, settings.external_api_max_retries)
        self.assertEqual(2.0, settings.external_api_retry_backoff_seconds)
        self.assertEqual(1, settings.external_api_max_connections)
        self.assertEqual(0, settings.external_api_max_keepalive_connections)


if __name__ == "__main__":
    unittest.main()
