"""Validated Agent definition catalog."""

from __future__ import annotations

import configparser
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.workspace import validate_identifier


class AgentDefinitionError(ValueError):
    pass


@dataclass(frozen=True)
class AgentResources:
    cpu_limit: float
    memory_mb: int
    pids_limit: int


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    display_name: str
    image: str
    idle_timeout_seconds: int
    resources: AgentResources
    default_model: str
    allowed_models: tuple[str, ...]
    path: Path
    opencode: dict[str, object]


class AgentCatalog:
    def __init__(self, root: str | Path, *, gateway_url: str = 'http://host.docker.internal:4001/v1') -> None:
        self.root = Path(root).expanduser().absolute()
        self.gateway_url = gateway_url
        try:
            self._root_real = self.root.resolve(strict=True)
        except OSError as exc:
            raise AgentDefinitionError(f"invalid Agent catalog root: {exc}") from exc
        if not self._root_real.is_dir():
            raise AgentDefinitionError("Agent catalog root must be a directory")

    def load(self, agent_id: str) -> AgentDefinition:
        try:
            validate_identifier(agent_id, "agent_id")
            path = (self.root / agent_id).resolve(strict=True)
        except (OSError, ValueError) as exc:
            raise AgentDefinitionError(f"unknown or invalid Agent {agent_id!r}: {exc}") from exc
        if not path.is_relative_to(self._root_real) or not path.is_dir():
            raise AgentDefinitionError("Agent definition escapes catalog root")
        parser = configparser.ConfigParser(interpolation=None)
        try:
            if parser.read(path / "agent.cfg", encoding="utf-8") != [str(path / "agent.cfg")]:
                raise AgentDefinitionError(f"missing agent.cfg for {agent_id}")
            configured_id = validate_identifier(parser.get("agent", "id"), "agent.id")
            if configured_id != agent_id:
                raise AgentDefinitionError("directory name and agent.id must match")
            image = parser.get("agent", "image")
            idle = parser.getint("agent", "idle_timeout_seconds")
            resources = AgentResources(
                parser.getfloat("resources", "cpu_limit"),
                parser.getint("resources", "memory_mb"),
                parser.getint("resources", "pids_limit"),
            )
            default = parser.get("models", "default")
            allowed = tuple(item.strip() for item in parser.get("models", "allowed").split(",") if item.strip())
            opencode = json.loads((path / "opencode.json").read_text(encoding="utf-8"))
        except (configparser.Error, KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, AgentDefinitionError):
                raise
            raise AgentDefinitionError(f"invalid Agent {agent_id}: {exc}") from exc
        if idle <= 0 or resources.cpu_limit <= 0 or resources.memory_mb <= 0 or resources.pids_limit <= 0:
            raise AgentDefinitionError("Agent timeouts and resources must be positive")
        if not allowed or default not in allowed or len(set(allowed)) != len(allowed):
            raise AgentDefinitionError("default model must occur once in a non-empty allowed list")
        self._validate_opencode(opencode, allowed, default, path, gateway_url=self.gateway_url)
        return AgentDefinition(
            configured_id, parser.get("agent", "display_name"), image, idle,
            resources, default, allowed, path, opencode,
        )

    @staticmethod
    def _validate_opencode(
        config: dict[str, object], allowed: tuple[str, ...], default: str, agent_path: Path,
        *, gateway_url: str = 'http://host.docker.internal:4001/v1'
    ) -> None:
        if config.get("share") != "disabled" or config.get("autoupdate") is not False:
            raise AgentDefinitionError("sharing must be disabled and autoupdate false")
        plugins = config.get("plugin", [])
        if not isinstance(plugins, list) or any(
            not isinstance(item, str) or not item.startswith("file://") for item in plugins
        ):
            raise AgentDefinitionError("only local file:// plugins are allowed")
        enabled = config.get("enabled_providers")
        if enabled != ["cloud-model-gateway"]:
            raise AgentDefinitionError("only cloud-model-gateway may be enabled")
        provider = config.get("provider")
        try:
            gateway = provider["cloud-model-gateway"]  # type: ignore[index]
            models = gateway["models"]  # type: ignore[index]
            base_url = gateway["options"]["baseURL"]  # type: ignore[index]
            package = gateway["npm"]  # type: ignore[index]
        except (KeyError, TypeError) as exc:
            raise AgentDefinitionError("cloud-model-gateway provider is incomplete") from exc
        if (
            not isinstance(models, dict)
            or set(models) != set(allowed)
            or base_url != gateway_url
            or package != "@ai-sdk/openai-compatible"
        ):
            raise AgentDefinitionError("provider models or local gateway URL do not match agent.cfg")
        if config.get("model") != f"cloud-model-gateway/{default}":
            raise AgentDefinitionError("OpenCode default model does not match agent.cfg")
        instructions = config.get("instructions")
        if not isinstance(instructions, list) or not instructions:
            raise AgentDefinitionError("instructions must reference local Agent files")
        for instruction in instructions:
            AgentCatalog._validate_local_reference(
                instruction, agent_path, prefix="/opt/agent/", allow_glob=True
            )
        for plugin in plugins:
            AgentCatalog._validate_local_reference(
                plugin, agent_path, prefix="file:///opt/agent/", allow_glob=False
            )

    @staticmethod
    def _validate_local_reference(
        value: object, agent_path: Path, *, prefix: str, allow_glob: bool
    ) -> None:
        if not isinstance(value, str) or not value.startswith(prefix):
            raise AgentDefinitionError(f"local reference must start with {prefix}")
        relative = value[len(prefix):]
        parts = PurePosixPath(relative).parts
        if not relative or ".." in parts or PurePosixPath(relative).is_absolute():
            raise AgentDefinitionError("local reference escapes Agent definition")
        if not allow_glob and any(character in relative for character in "*?["):
            raise AgentDefinitionError("plugin references cannot contain globs")
        try:
            matches = list(agent_path.glob(relative)) if allow_glob else [agent_path / relative]
        except (OSError, ValueError) as exc:
            raise AgentDefinitionError(f"invalid local reference {value!r}: {exc}") from exc
        if not matches:
            raise AgentDefinitionError(f"missing local reference: {value}")
        for match in matches:
            try:
                resolved = match.resolve(strict=True)
            except OSError as exc:
                raise AgentDefinitionError(f"missing local reference: {value}") from exc
            if not resolved.is_relative_to(agent_path) or not resolved.is_file():
                raise AgentDefinitionError(f"local reference is outside Agent definition: {value}")

    def load_all(self) -> dict[str, AgentDefinition]:
        return {
            child.name: self.load(child.name)
            for child in sorted(self.root.iterdir())
            if child.is_dir() and not child.name.startswith(".")
        }
