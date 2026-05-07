from datetime import date

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

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
    )
    query: str = Field(validation_alias=AliasChoices("query", "especialidade"))


class SearchProvidersResponse(BaseModel):
    providers: list[Provider]


class HandoffHumanRequest(ToolBase):
    reason: str


class HandoffHumanResponse(BaseModel):
    status: CallFinalState
    reason: str
