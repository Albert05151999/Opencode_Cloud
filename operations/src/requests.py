"""Public workflow inputs; internal execution flags cannot be supplied by clients."""

from pydantic import BaseModel, ConfigDict, Field
from fastapi import HTTPException


class OperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=128)
    revision: int | None = None


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str | None = Field(default=None, min_length=8, max_length=128)
    revision: int | None = None
    version: int | None = Field(default=None, ge=1)


class DeleteRequest(OperationRequest):
    preview_id: str
    confirmation: str


class SandboxRequest(OperationRequest):
    force_preview_id: str | None = None
    confirmation: str | None = None


def parse(model, payload):
    from pydantic import ValidationError

    try:
        return model.model_validate(payload).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(
            422, exc.errors(include_context=False, include_input=False)
        ) from exc
