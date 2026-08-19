from functools import lru_cache
import json
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_PLACEHOLDER_MARKERS = (
    "replace-with",
    "replace_with",
    "changeme",
    "change-me",
    "placeholder",
    "example.com",
    ".example",
    "seudominio.com",
    "<",
    ">",
)


def _looks_like_placeholder(value: object) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _PLACEHOLDER_MARKERS)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "Integrix AI Call Center Pilot"
    environment: str = "dev"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/integrix"
    db_enabled: bool = False
    db_connect_timeout_seconds: float = 2.0
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_seconds: float = 5.0
    db_pool_recycle_seconds: int = 1800
    data_mode: Literal["mock", "external_api", "protheus"] = "mock"
    default_tenant: str = "demo"
    tenant_map: dict[str, str] = Field(default_factory=dict)
    tenant_assistant_map: dict[str, str] = Field(default_factory=dict)
    tenant_phone_number_map: dict[str, str] = Field(default_factory=dict)
    default_tenant_implementation: str = "pbsaude"
    tenant_implementation_map: dict[str, str] = Field(default_factory=dict)
    chaos_error_rate: float = 0.0
    chaos_latency_ms: int = 0
    log_level: str = "INFO"
    auth_max_attempts: int = 2
    # Legacy naming kept for backward compatibility.
    protheus_base_url: str | None = None
    external_api_base_url: str | None = None
    external_api_auth_type: Literal["none", "bearer", "basic"] = "none"
    external_api_token: str | None = None
    external_api_username: str | None = None
    external_api_password: str | None = None
    external_api_provider_search_path: str = "/rest02/TNSCallCenter/busca-rede"
    external_api_timeout_seconds: float = 3.0
    external_api_max_retries: int = 1
    external_api_retry_backoff_seconds: float = 0.2
    external_api_max_connections: int = 50
    external_api_max_keepalive_connections: int = 20
    provider_max_results: int = 3
    pbsaude_provider_policy_enabled: bool = False
    external_api_tenant_configs: dict[str, dict[str, str | float | bool | None]] = Field(
        default_factory=dict
    )
    auth_timeout_seconds: float = 2.0
    status_timeout_seconds: float = 2.0
    provider_timeout_seconds: float = 2.0
    webhook_secret: str | None = None
    webhook_secret_header: str = "x-webhook-secret"
    specialties_csv_path: str | None = None
    vapi_api_key: str | None = None
    vapi_base_url: str = "https://api.vapi.ai"
    vapi_calls_path: str = "/call"
    ops_dashboard_token: str | None = None
    ops_token_header: str = "x-ops-token"
    ops_cost_sync_page_size: int = 100
    ops_cost_sync_lookback_minutes: int = 60
    ops_cost_sync_enabled: bool = True
    ops_cost_v2_enabled: bool = False
    ops_cost_sync_interval_seconds: int = 300
    ops_cost_sync_overlap_minutes: int = 10
    ops_cost_backfill_days: int = 90
    ops_session_max_age_seconds: int = 28800
    ops_login_max_attempts: int = 5
    ops_login_window_minutes: int = 15
    ptax_base_url: str = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata"
    daily_report_enabled: bool = False
    daily_report_recipients: str = ""
    daily_report_tenant_id: str | None = None
    daily_report_assistant_id: str | None = None
    daily_report_period_days: int = 7
    daily_report_hour_brasilia: int = 7
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_starttls: bool = True
    smtp_use_ssl: bool = False
    audit_write_mode: Literal["sync", "async"] = "sync"
    audit_queue_max_size: int = 10000
    audit_batch_size: int = 100
    audit_flush_interval_seconds: float = 1.0
    ops_allow_global_queries: bool = False
    call_events_retention_days: int = 90
    vapi_cost_retention_days: int = 365

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @field_validator("tenant_map", mode="before")
    @classmethod
    def parse_tenant_map(cls, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError("TENANT_MAP must be a valid JSON object string") from exc
        return value

    @field_validator("tenant_assistant_map", mode="before")
    @classmethod
    def parse_tenant_assistant_map(cls, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError("TENANT_ASSISTANT_MAP must be a valid JSON object string") from exc
        return value

    @field_validator("tenant_phone_number_map", mode="before")
    @classmethod
    def parse_tenant_phone_number_map(cls, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError("TENANT_PHONE_NUMBER_MAP must be a valid JSON object string") from exc
        return value

    @field_validator("external_api_tenant_configs", mode="before")
    @classmethod
    def parse_external_api_tenant_configs(cls, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError("EXTERNAL_API_TENANT_CONFIGS must be a valid JSON object string") from exc
        return value

    @field_validator("tenant_implementation_map", mode="before")
    @classmethod
    def parse_tenant_implementation_map(cls, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError("TENANT_IMPLEMENTATION_MAP must be a valid JSON object string") from exc
        return value

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: str | None) -> str:
        return (value or "dev").strip()

    @field_validator("chaos_error_rate")
    @classmethod
    def clamp_error_rate(cls, value):
        return max(0.0, min(1.0, value))

    @field_validator("data_mode", mode="before")
    @classmethod
    def normalize_data_mode(cls, value: str):
        if value == "protheus":
            return "external_api"
        return value

    @field_validator("webhook_secret", mode="before")
    @classmethod
    def normalize_webhook_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("webhook_secret_header")
    @classmethod
    def normalize_secret_header(cls, value: str) -> str:
        # FastAPI/Starlette expose headers case-insensitively; normalize to lowercase key.
        return value.strip().lower()

    @field_validator("ops_token_header")
    @classmethod
    def normalize_ops_token_header(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("daily_report_recipients", mode="before")
    @classmethod
    def normalize_daily_report_recipients(cls, value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            values = [str(item) for item in value]
        else:
            values = str(value).replace(";", ",").split(",")
        return ",".join(item.strip() for item in values if item and item.strip())

    @field_validator("ops_cost_sync_page_size")
    @classmethod
    def clamp_ops_cost_sync_page_size(cls, value: int) -> int:
        return max(1, min(1000, value))

    @field_validator("ops_cost_sync_lookback_minutes")
    @classmethod
    def clamp_ops_cost_sync_lookback_minutes(cls, value: int) -> int:
        return max(1, min(10080, value))

    @field_validator("ops_cost_sync_interval_seconds")
    @classmethod
    def clamp_ops_cost_sync_interval_seconds(cls, value: int) -> int:
        return max(60, min(3600, value))

    @field_validator("ops_cost_sync_overlap_minutes")
    @classmethod
    def clamp_ops_cost_sync_overlap_minutes(cls, value: int) -> int:
        return max(1, min(1440, value))

    @field_validator("ops_cost_backfill_days")
    @classmethod
    def clamp_ops_cost_backfill_days(cls, value: int) -> int:
        return max(1, min(365, value))

    @field_validator("ops_session_max_age_seconds")
    @classmethod
    def clamp_ops_session_max_age_seconds(cls, value: int) -> int:
        return max(900, min(86400, value))

    @field_validator("ops_login_max_attempts")
    @classmethod
    def clamp_ops_login_max_attempts(cls, value: int) -> int:
        return max(3, min(20, value))

    @field_validator("ops_login_window_minutes")
    @classmethod
    def clamp_ops_login_window_minutes(cls, value: int) -> int:
        return max(1, min(60, value))

    @field_validator("daily_report_period_days")
    @classmethod
    def validate_daily_report_period_days(cls, value: int) -> int:
        if value not in {7, 15, 30, 90}:
            raise ValueError("DAILY_REPORT_PERIOD_DAYS must be one of: 7, 15, 30, 90")
        return value

    @field_validator("daily_report_hour_brasilia")
    @classmethod
    def validate_daily_report_hour_brasilia(cls, value: int) -> int:
        if not 0 <= value <= 23:
            raise ValueError("DAILY_REPORT_HOUR_BRASILIA must be between 0 and 23")
        return value

    @field_validator("smtp_port")
    @classmethod
    def validate_smtp_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("SMTP_PORT must be between 1 and 65535")
        return value

    @field_validator("db_connect_timeout_seconds")
    @classmethod
    def clamp_db_connect_timeout_seconds(cls, value: float) -> float:
        return max(0.5, min(10.0, value))

    @field_validator("db_pool_size")
    @classmethod
    def clamp_db_pool_size(cls, value: int) -> int:
        return max(1, min(100, value))

    @field_validator("db_max_overflow")
    @classmethod
    def clamp_db_max_overflow(cls, value: int) -> int:
        return max(0, min(200, value))

    @field_validator("db_pool_timeout_seconds")
    @classmethod
    def clamp_db_pool_timeout_seconds(cls, value: float) -> float:
        return max(0.5, min(60.0, value))

    @field_validator("db_pool_recycle_seconds")
    @classmethod
    def clamp_db_pool_recycle_seconds(cls, value: int) -> int:
        return max(60, min(86400, value))

    @field_validator("audit_queue_max_size")
    @classmethod
    def clamp_audit_queue_max_size(cls, value: int) -> int:
        return max(1, min(1_000_000, value))

    @field_validator("audit_batch_size")
    @classmethod
    def clamp_audit_batch_size(cls, value: int) -> int:
        return max(1, min(1000, value))

    @field_validator("audit_flush_interval_seconds")
    @classmethod
    def clamp_audit_flush_interval_seconds(cls, value: float) -> float:
        return max(0.05, min(10.0, value))

    @field_validator("call_events_retention_days", "vapi_cost_retention_days")
    @classmethod
    def clamp_retention_days(cls, value: int) -> int:
        return max(1, min(3650, value))

    @field_validator("provider_max_results")
    @classmethod
    def clamp_provider_max_results(cls, value: int) -> int:
        return max(1, min(10, value))

    @field_validator("external_api_max_retries")
    @classmethod
    def clamp_external_api_max_retries(cls, value: int) -> int:
        return max(0, min(3, value))

    @field_validator("external_api_retry_backoff_seconds")
    @classmethod
    def clamp_external_api_retry_backoff_seconds(cls, value: float) -> float:
        return max(0.0, min(2.0, value))

    @field_validator("external_api_max_connections")
    @classmethod
    def clamp_external_api_max_connections(cls, value: int) -> int:
        return max(1, min(500, value))

    @field_validator("external_api_max_keepalive_connections")
    @classmethod
    def clamp_external_api_max_keepalive_connections(cls, value: int) -> int:
        return max(0, min(500, value))

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.daily_report_enabled:
            daily_report_missing: list[str] = []
            recipients = self.daily_report_recipient_list
            if not self.db_enabled:
                daily_report_missing.append("DB_ENABLED=true")
            if not self.daily_report_tenant_id or not self.daily_report_tenant_id.strip():
                daily_report_missing.append("DAILY_REPORT_TENANT_ID")
            if not recipients:
                daily_report_missing.append("DAILY_REPORT_RECIPIENTS")
            if not self.smtp_host or not self.smtp_host.strip():
                daily_report_missing.append("SMTP_HOST")
            if not self.smtp_from_email or not self.smtp_from_email.strip():
                daily_report_missing.append("SMTP_FROM_EMAIL")
            if bool(self.smtp_username) != bool(self.smtp_password):
                daily_report_missing.append("SMTP_USERNAME/SMTP_PASSWORD")
            if self.smtp_use_starttls and self.smtp_use_ssl:
                daily_report_missing.append("only one of SMTP_USE_STARTTLS or SMTP_USE_SSL")
            invalid_recipients = [recipient for recipient in recipients if "@" not in recipient]
            if invalid_recipients:
                daily_report_missing.append("valid DAILY_REPORT_RECIPIENTS")
            smtp_placeholders = [
                name
                for name, value in [
                    ("SMTP_HOST", self.smtp_host),
                    ("SMTP_USERNAME", self.smtp_username),
                    ("SMTP_PASSWORD", self.smtp_password),
                    ("SMTP_FROM_EMAIL", self.smtp_from_email),
                ]
                if _looks_like_placeholder(value)
            ]
            if smtp_placeholders:
                daily_report_missing.append(
                    "placeholder SMTP values: " + ", ".join(smtp_placeholders)
                )
            if daily_report_missing:
                raise ValueError(
                    "Invalid daily report settings: " + ", ".join(daily_report_missing)
                )

        if not self.is_production:
            return self

        missing: list[str] = []
        if not self.webhook_secret:
            missing.append("WEBHOOK_SECRET")
        if self.data_mode != "external_api":
            missing.append("DATA_MODE=external_api")
        if not self.db_enabled:
            missing.append("DB_ENABLED=true")
        if self.audit_write_mode != "async":
            missing.append("AUDIT_WRITE_MODE=async")
        if not (self.tenant_map or self.tenant_assistant_map or self.tenant_phone_number_map):
            missing.append("TENANT_MAP or TENANT_ASSISTANT_MAP or TENANT_PHONE_NUMBER_MAP")
        if not self.ops_dashboard_token:
            missing.append("OPS_DASHBOARD_TOKEN")
        if not (self.external_api_base_url or self.protheus_base_url or self.external_api_tenant_configs):
            missing.append("EXTERNAL_API_BASE_URL")
        if self.external_api_auth_type == "none":
            missing.append("EXTERNAL_API_AUTH_TYPE")
        if self.external_api_auth_type == "bearer" and not self.external_api_token:
            missing.append("EXTERNAL_API_TOKEN")
        if self.external_api_auth_type == "basic" and (
            not self.external_api_username or not self.external_api_password
        ):
            missing.append("EXTERNAL_API_USERNAME/EXTERNAL_API_PASSWORD")
        if self.chaos_error_rate != 0:
            missing.append("CHAOS_ERROR_RATE=0")
        if self.chaos_latency_ms != 0:
            missing.append("CHAOS_LATENCY_MS=0")
        if "localhost" in self.database_url.lower():
            missing.append("non-local DATABASE_URL")

        placeholder_fields = [
            ("DATABASE_URL", self.database_url),
            ("WEBHOOK_SECRET", self.webhook_secret),
            ("OPS_DASHBOARD_TOKEN", self.ops_dashboard_token),
            ("EXTERNAL_API_BASE_URL", self.external_api_base_url),
            ("PROTHEUS_BASE_URL", self.protheus_base_url),
            ("EXTERNAL_API_TOKEN", self.external_api_token),
            ("EXTERNAL_API_USERNAME", self.external_api_username),
            ("EXTERNAL_API_PASSWORD", self.external_api_password),
            ("VAPI_API_KEY", self.vapi_api_key),
        ]
        placeholders = [name for name, value in placeholder_fields if _looks_like_placeholder(value)]
        if placeholders:
            missing.append("placeholder production values: " + ", ".join(placeholders))

        if missing:
            raise ValueError(
                "Invalid production settings: " + ", ".join(missing)
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def daily_report_recipient_list(self) -> tuple[str, ...]:
        return tuple(
            recipient.strip()
            for recipient in self.daily_report_recipients.split(",")
            if recipient.strip()
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
