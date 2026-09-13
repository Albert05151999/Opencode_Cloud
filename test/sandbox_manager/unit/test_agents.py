from __future__ import annotations

import json
from pathlib import Path

import pytest

from sandbox_manager.agents import AgentCatalog, AgentDefinitionError


REPOSITORY_AGENTS = Path(__file__).resolve().parents[3] / "agent_runtime/resources/agents"
FIXED_IMAGE = "sha256:c4166f5dfd4264e71685ebafe2729148f32e414e38508b277e3a357fb472fc66"
GATEWAY_URL = "http://host.docker.internal:4001/v1"


def test_repository_catalog_parses_exact_agent_contracts() -> None:
    definitions = AgentCatalog(REPOSITORY_AGENTS).load_all()

    assert set(definitions) == {"agent-code", "agent-data"}
    expected = {
        "agent-code": ("coding-fast", ("coding-fast", "coding-quality")),
        "agent-data": ("data-fast", ("data-fast", "data-quality")),
    }
    assert {definition.image for definition in definitions.values()} == {FIXED_IMAGE}

    for agent_id, definition in definitions.items():
        default, allowed = expected[agent_id]
        assert definition.agent_id == agent_id
        assert definition.default_model == default
        assert definition.allowed_models == allowed
        assert definition.idle_timeout_seconds > 0
        assert definition.resources.cpu_limit > 0
        assert definition.resources.memory_mb > 0
        assert definition.resources.pids_limit > 0

        opencode = definition.opencode
        provider = opencode["provider"]["cloud-model-gateway"]
        assert provider["options"]["baseURL"] == GATEWAY_URL
        assert set(provider["models"]) == set(allowed)
        assert opencode["model"] == f"cloud-model-gateway/{default}"
        assert opencode["share"] == "disabled"
        assert opencode["autoupdate"] is False
        assert all(item.startswith("file://") for item in opencode["plugin"])

        assert (definition.path / "AGENTS.md").is_file()
        skill_files = sorted((definition.path / "skills").glob("*/SKILL.md"))
        assert skill_files
        assert all(path.is_file() for path in skill_files)
        assert opencode["instructions"] == [
            "/opt/agent/AGENTS.md",
            "/opt/agent/skills/*/SKILL.md",
        ]


def valid_opencode(default: str = "coding-fast") -> dict[str, object]:
    return {
        "share": "disabled",
        "autoupdate": False,
        "plugin": [],
        "model": f"cloud-model-gateway/{default}",
        "instructions": ["/opt/agent/AGENTS.md", "/opt/agent/skills/*/SKILL.md"],
        "enabled_providers": ["cloud-model-gateway"],
        "provider": {
            "cloud-model-gateway": {
                "npm": "@ai-sdk/openai-compatible",
                "options": {"baseURL": GATEWAY_URL},
                "models": {
                    "coding-fast": {"name": "Coding Fast"},
                    "coding-quality": {"name": "Coding Quality"},
                },
            }
        },
    }


def write_agent(
    root: Path,
    *,
    directory: str = "agent-code",
    configured_id: str = "agent-code",
    default: str = "coding-fast",
    allowed: str = "coding-fast,coding-quality",
    cpu: str = "1.0",
    memory: str = "512",
    pids: str = "64",
    opencode: dict[str, object] | None = None,
    write_cfg: bool = True,
    write_json: bool = True,
) -> Path:
    path = root / directory
    path.mkdir(parents=True)
    if write_cfg:
        (path / "agent.cfg").write_text(
            (
                "[agent]\n"
                f"id = {configured_id}\n"
                "display_name = Test Agent\n"
                "image = runtime:test\n"
                "idle_timeout_seconds = 60\n\n"
                "[resources]\n"
                f"cpu_limit = {cpu}\n"
                f"memory_mb = {memory}\n"
                f"pids_limit = {pids}\n\n"
                "[models]\n"
                f"default = {default}\n"
                f"allowed = {allowed}\n"
            ),
            encoding="utf-8",
        )
    if write_json:
        (path / "opencode.json").write_text(
            json.dumps(opencode if opencode is not None else valid_opencode(default)),
            encoding="utf-8",
        )
    (path / "AGENTS.md").write_text("instructions", encoding="utf-8")
    skill = path / "skills" / "test"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("skill", encoding="utf-8")
    return path


def test_rejects_directory_and_configured_agent_id_mismatch(tmp_path: Path) -> None:
    write_agent(tmp_path, directory="directory-id", configured_id="configured-id")
    with pytest.raises(AgentDefinitionError, match="directory name"):
        AgentCatalog(tmp_path).load("directory-id")


def test_rejects_default_model_outside_allowed_list(tmp_path: Path) -> None:
    write_agent(tmp_path, default="coding-other")
    with pytest.raises(AgentDefinitionError, match="default model"):
        AgentCatalog(tmp_path).load("agent-code")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value["provider"]["cloud-model-gateway"]["models"].pop(
                "coding-quality"
            ),
            "provider models",
        ),
        (
            lambda value: value["provider"]["cloud-model-gateway"]["options"].update(
                {"baseURL": "https://remote.example/v1"}
            ),
            "provider models",
        ),
        (
            lambda value: value.update(
                {"plugin": ["https://plugins.example/plugin.js"]}
            ),
            "only local",
        ),
        (
            lambda value: value.update({"plugin": ["@scope/remote-plugin"]}),
            "only local",
        ),
        (
            lambda value: value.update({"plugin": ["/opt/agent/plugin.py"]}),
            "only local",
        ),
        (lambda value: value.update({"share": "manual"}), "sharing must be disabled"),
        (lambda value: value.update({"share": True}), "sharing must be disabled"),
        (lambda value: value.update({"autoupdate": True}), "sharing must be disabled"),
        (
            lambda value: value["provider"]["cloud-model-gateway"].update(
                {"npm": "remote-package"}
            ),
            "provider models",
        ),
    ],
)
def test_rejects_unsafe_opencode_configuration(
    tmp_path: Path, mutation, message: str
) -> None:
    opencode = valid_opencode()
    mutation(opencode)
    write_agent(tmp_path, opencode=opencode)
    with pytest.raises(AgentDefinitionError, match=message):
        AgentCatalog(tmp_path).load("agent-code")


@pytest.mark.parametrize(
    ("write_cfg", "write_json", "message"),
    [
        (False, True, "missing agent.cfg"),
        (True, False, "invalid Agent"),
    ],
)
def test_rejects_missing_required_files(
    tmp_path: Path, write_cfg: bool, write_json: bool, message: str
) -> None:
    write_agent(tmp_path, write_cfg=write_cfg, write_json=write_json)
    with pytest.raises(AgentDefinitionError, match=message):
        AgentCatalog(tmp_path).load("agent-code")


@pytest.mark.parametrize(
    ("cpu", "memory", "pids"),
    [
        ("0", "512", "64"),
        ("-1", "512", "64"),
        ("1", "0", "64"),
        ("1", "512", "-1"),
        ("not-a-number", "512", "64"),
    ],
)
def test_rejects_zero_negative_or_invalid_resources(
    tmp_path: Path, cpu: str, memory: str, pids: str
) -> None:
    write_agent(tmp_path, cpu=cpu, memory=memory, pids=pids)
    with pytest.raises(AgentDefinitionError):
        AgentCatalog(tmp_path).load("agent-code")


@pytest.mark.parametrize("agent_id", ["../outside", "/absolute", "missing-agent"])
def test_rejects_unsafe_or_missing_agent_paths(
    tmp_path: Path, agent_id: str
) -> None:
    write_agent(tmp_path)
    with pytest.raises(AgentDefinitionError, match="unknown or invalid Agent"):
        AgentCatalog(tmp_path).load(agent_id)


def test_rejects_missing_instruction_resource(tmp_path: Path) -> None:
    path = write_agent(tmp_path)
    (path / "AGENTS.md").unlink()
    with pytest.raises(AgentDefinitionError, match="missing local reference"):
        AgentCatalog(tmp_path).load("agent-code")
