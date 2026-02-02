from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..utils.enums import AuthLevel, AuthorizationStatus, CallFinalState


class ToolBase(BaseModel):
    call_id: str | None = Field(default=None, description="Unique call identifier")
    to_number: str | None = Field(default=None, description="Dialed DID (resolves tenant)")

    model_config = ConfigDict(extra="forbid")


class AuthenticateRequest(ToolBase):
    cpf: str
    birthdate: date


class AuthenticateResponse(BaseModel):
    member_id: str
    auth_level: AuthLevel

    model_config = ConfigDict(extra="ignore")


class AuthorizationStatusRequest(ToolBase):
    member_id: str
    guia_id: str


class AuthorizationStatusResponse(BaseModel):
    status: AuthorizationStatus


class Provider(BaseModel):
    name: str
    specialty: str
    address: str
    city: str
    neighborhood: str | None = None
    phone: str


class SearchProvidersRequest(ToolBase):
    city: str
    neighborhood: str | None = None
    query: str


class SearchProvidersResponse(BaseModel):
    providers: list[Provider]


class HandoffHumanRequest(ToolBase):
    reason: str


class HandoffHumanResponse(BaseModel):
    status: CallFinalState
    reason: str


class VapiFunction(BaseModel):
    name: str
    arguments: Any

    model_config = ConfigDict(extra="ignore")


class VapiToolCall(BaseModel):
    id: str | None = None
    function: VapiFunction

    model_config = ConfigDict(extra="ignore")


class VapiCall(BaseModel):
    id: str | None = None
    to: str | None = None

    model_config = ConfigDict(extra="ignore")


class VapiMessage(BaseModel):
    call: VapiCall
    toolCallList: list[VapiToolCall]

    model_config = ConfigDict(extra="ignore")


class ToolInvocationRequest(BaseModel):
    message: VapiMessage

    model_config = ConfigDict(extra="ignore")


class ToolError(BaseModel):
    code: Literal["TIMEOUT", "VALIDATION", "UPSTREAM_503"]
    message: str


class ToolResponse(BaseModel):
    ok: bool
    tool_name: str | None = None
    data: dict | None = None
    error: ToolError | None = None
    final_state: CallFinalState
