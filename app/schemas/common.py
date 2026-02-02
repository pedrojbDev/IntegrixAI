from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base schema with strict extras disabled."""

    model_config = ConfigDict(extra="forbid")

