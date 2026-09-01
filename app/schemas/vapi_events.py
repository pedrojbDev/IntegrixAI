from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class VapiServerEvent(BaseModel):
    """Forward-compatible Vapi server-event envelope.

    Event-specific data remains an untyped mapping because Vapi evolves the
    payload by event type. The ingestion service performs the semantic checks.
    """

    message: dict[str, Any]

    model_config = ConfigDict(extra="ignore")

    @field_validator("message")
    @classmethod
    def require_event_type(cls, value: dict[str, Any]) -> dict[str, Any]:
        event_type = value.get("type")
        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("message.type is required")
        return value
