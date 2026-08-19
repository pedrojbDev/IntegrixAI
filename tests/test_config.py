import unittest

from pydantic import ValidationError

from app.config import Settings


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
        "chaos_error_rate": 0.0,
        "chaos_latency_ms": 0,
    }
    values.update(overrides)
    return Settings(**values)


class SettingsTests(unittest.TestCase):
    def test_pbsaude_provider_policy_is_opt_in(self) -> None:
        self.assertFalse(Settings(_env_file=None).pbsaude_provider_policy_enabled)
        self.assertTrue(
            Settings(
                _env_file=None,
                pbsaude_provider_policy_enabled=True,
            ).pbsaude_provider_policy_enabled
        )

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

    def test_production_requires_explicit_tenant_resolution_map(self) -> None:
        with self.assertRaisesRegex(ValidationError, "TENANT_MAP or TENANT_ASSISTANT_MAP"):
            production_settings(tenant_map={})

    def test_production_accepts_tenant_assistant_map_without_did_map(self) -> None:
        settings = production_settings(
            tenant_map={},
            tenant_assistant_map={"assistant_123": "tenant_a"},
        )

        self.assertEqual({"assistant_123": "tenant_a"}, settings.tenant_assistant_map)

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

    def test_production_rejects_placeholder_secrets(self) -> None:
        with self.assertRaisesRegex(ValidationError, "placeholder production values"):
            production_settings(webhook_secret="replace-with-strong-vapi-webhook-secret")

    def test_production_rejects_placeholder_external_api_values(self) -> None:
        with self.assertRaisesRegex(ValidationError, "placeholder production values"):
            production_settings(
                database_url="postgresql+psycopg://integrix:replace-with-strong-postgres-password@postgres:5432/integrix",
                external_api_base_url="https://customer-api.example",
                external_api_username="replace-with-upstream-user",
                external_api_password="replace-with-upstream-password",
            )

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

    def test_daily_report_normalizes_recipient_list(self) -> None:
        settings = Settings(
            _env_file=None,
            db_enabled=True,
            daily_report_enabled=True,
            daily_report_tenant_id="tenant_a",
            daily_report_recipients="pedro@example.com; ops@example.com",
            smtp_host="smtp.mail.test",
            smtp_from_email="reports@integrix.test",
        )

        self.assertEqual(
            ("pedro@example.com", "ops@example.com"),
            settings.daily_report_recipient_list,
        )
        self.assertEqual(7, settings.daily_report_period_days)
        self.assertEqual(7, settings.daily_report_hour_brasilia)

    def test_daily_report_requires_delivery_configuration_when_enabled(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Invalid daily report settings"):
            Settings(_env_file=None, daily_report_enabled=True, db_enabled=True)

    def test_daily_report_rejects_unsupported_period(self) -> None:
        with self.assertRaisesRegex(ValidationError, "DAILY_REPORT_PERIOD_DAYS"):
            Settings(_env_file=None, daily_report_period_days=14)


if __name__ == "__main__":
    unittest.main()
