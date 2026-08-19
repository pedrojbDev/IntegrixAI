from pydantic import BaseModel, ConfigDict


class CommonSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
