from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ...utils.enums import CallFinalState


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
