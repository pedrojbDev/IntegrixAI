from functools import lru_cache
import json
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    provider_max_results: int = 3
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

    @field_validator("ops_cost_sync_page_size")
    @classmethod
    def clamp_ops_cost_sync_page_size(cls, value: int) -> int:
        return max(1, min(200, value))

    @field_validator("ops_cost_sync_lookback_minutes")
    @classmethod
    def clamp_ops_cost_sync_lookback_minutes(cls, value: int) -> int:
        return max(1, min(10080, value))

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

    @model_validator(mode="after")
    def validate_production_settings(self):
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
        if not self.tenant_map:
            missing.append("TENANT_MAP")
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

        if missing:
            raise ValueError(
                "Invalid production settings: " + ", ".join(missing)
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
