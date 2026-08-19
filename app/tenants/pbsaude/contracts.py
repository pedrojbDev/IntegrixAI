from datetime import date

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from ...utils.enums import AuthLevel, AuthorizationStatus, CallFinalState


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
    cpf: str | None = None
    tipo_atendimento: str | None = Field(
        default=None,
        validation_alias=AliasChoices("tipo_atendimento", "tipoAtendimento"),
    )
    city: str = Field(validation_alias=AliasChoices("city", "cidade"))
    neighborhood: str | None = Field(
        default=None,
        validation_alias=AliasChoices("neighborhood", "bairro"),
        description=(
            "Legacy Vapi input accepted during migration; ignored by provider search "
            "and never sent to the upstream API"
        ),
    )
    query: str = Field(validation_alias=AliasChoices("query", "especialidade"))

    @field_validator("city", "query", mode="before")
    @classmethod
    def strip_required_text(cls, value):
        if value is None:
            return value
        return str(value).strip()

    @field_validator("neighborhood", "tipo_atendimento", mode="before")
    @classmethod
    def strip_optional_text(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class SearchProvidersResponse(BaseModel):
    providers: list[Provider]


class HandoffHumanRequest(ToolBase):
    reason: str


class HandoffHumanResponse(BaseModel):
    status: CallFinalState
    reason: str
