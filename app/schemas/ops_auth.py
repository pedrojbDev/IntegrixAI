from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

OpsRole = Literal["platform_admin", "tenant_user"]


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 320 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("email invalido")
    return email


class OpsLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str = Field(min_length=8, max_length=256)

    _email = field_validator("email")(_normalize_email)


class OpsBootstrapRequest(OpsLoginRequest):
    token: str = Field(min_length=1)


class OpsPasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=8, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class OpsPrincipalResponse(BaseModel):
    id: str
    email: str
    role: OpsRole
    tenant_ids: list[str]
    must_change_password: bool


class OpsSessionResponse(BaseModel):
    authenticated: Literal[True] = True
    principal: OpsPrincipalResponse


class OpsUserBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    role: OpsRole
    tenant_ids: list[str] = Field(default_factory=list)

    _email = field_validator("email")(_normalize_email)

    @field_validator("tenant_ids")
    @classmethod
    def normalize_tenant_ids(cls, values: list[str]) -> list[str]:
        return sorted({value.strip() for value in values if value.strip()})


class OpsUserCreate(OpsUserBase):
    pass


class OpsUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: OpsRole | None = None
    tenant_ids: list[str] | None = None
    is_active: bool | None = None

    @field_validator("tenant_ids")
    @classmethod
    def normalize_tenant_ids(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return sorted({value.strip() for value in values if value.strip()})


class OpsUserResponse(OpsUserBase):
    id: str
    is_active: bool
    must_change_password: bool
    created_at: datetime
    updated_at: datetime


class OpsUserCreatedResponse(BaseModel):
    user: OpsUserResponse
    temporary_password: str


class OpsPasswordResetResponse(BaseModel):
    temporary_password: str
