"""Management request schemas shared by validation and generated OpenAPI."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

ResourceID = Annotated[str, Field(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$')]


class DTO(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ModelDefinition(DTO):
    id: ResourceID
    name: str = ''
    provider: Literal['openai-compatible', 'openai', 'anthropic', 'google', 'legacy']
    upstream_model: str = Field(min_length=1)
    base_url: str = ''
    api_key: str = ''
    headers: dict[str, str] = Field(default_factory=dict)
    parameters: dict[str, int | float | str] = Field(default_factory=dict)
    context: int | None = Field(default=None, gt=0)
    output: int | None = Field(default=None, gt=0)
    enabled: bool = True
    legacy: bool = False


class VersionBinding(DTO):
    id: ResourceID
    version: int = Field(gt=0)


class AgentDefinition(DTO):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=4000)
    enabled: bool = True
    instructions: str = Field(default='', max_length=200000)
    allowed_model_ids: list[ResourceID] = Field(min_length=1)
    default_model_id: ResourceID
    small_model_id: ResourceID | None = None
    bindings: list[VersionBinding] = Field(default_factory=list)


class Revision(DTO):
    revision: int | None = None


class ModelWrite(Revision):
    model: ModelDefinition


class ModelImport(Revision):
    models: list[ModelDefinition] = Field(min_length=1, max_length=100)
    replace: bool = False


class AgentWrite(Revision):
    config: AgentDefinition


class BindingWrite(Revision):
    bindings: list[VersionBinding] | None = None
    allowed_model_ids: list[ResourceID] | None = None
    default_model_id: ResourceID | None = None
    small_model_id: ResourceID | None = None


class ApplyRequest(Revision):
    version: int | None = Field(default=None, gt=0)


class CopyRequest(Revision):
    id: ResourceID
    owner: ResourceID | None = None


class ResourceDefinition(BaseModel):
    # Read-only catalog fields may be sent back by an editor; never persist them.
    model_config = ConfigDict(extra='ignore')
    kind: Literal['mcp', 'skill', 'hook']
    name: ResourceID
    owner: ResourceID | None = None
    archived: bool = False
    data: dict


class ResourceWrite(Revision):
    resource: ResourceDefinition


class ProbeRequest(DTO):
    agent_id: ResourceID | None = None
