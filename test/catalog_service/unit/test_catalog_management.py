import copy
import io
import json
import stat
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from catalog_service.src.management import (
    ManagementStore,
    unpack_skill,
    validate_mcp,
    redact,
)
from catalog_service.src.compiler import Compiler as ManagementRuntime
from catalog_service.src.admin_api import create_admin_router

ROOT = Path(__file__).resolve().parents[3] / "catalog_service/resources"
SKILL = b"---\nname: sample\ndescription: Test skill\n---\nUse this skill."


@pytest.fixture
def store(tmp_path):
    value = ManagementStore(tmp_path / "management", ROOT / "agents")
    from test.catalog_service.legacy_fixture import populate_legacy
    populate_legacy(value)
    with value.edit() as data:
        for model in data["models"].values():
            model["enabled"] = True
        for agent in data["agents"].values():
            agent["draft"]["enabled"] = True
            agent["versions"][0]["config"]["enabled"] = True
    return value


def test_fresh_bootstrap_is_empty_and_preserves_existing_configuration(tmp_path):
    root = tmp_path / "management"
    store = ManagementStore(root, ROOT / "agents")
    _, data = store.read()
    assert data["models"] == {} and data["agents"] == {} and data["resources"] == {}
    assert set(data["agent_templates"]) == {"example-code", "example-data"}
    with store.edit() as existing:
        existing["models"]["user-model"] = {"id": "user-model", "enabled": False}
    reopened = ManagementStore(root, ROOT / "agents")
    assert "user-model" in reopened.read()[1]["models"]


def test_disabled_legacy_is_skipped_but_enabled_legacy_still_requires_environment(
    tmp_path,
):
    fresh = ManagementStore(tmp_path / "management", ROOT / "agents")
    _, data = fresh.read()
    assert ManagementRuntime.gateway_configuration(None, data["models"], {})[
        "model_list"
    ] == []
    enabled = copy.deepcopy(data["models"])
    enabled["glm"] = {"id": "glm", "legacy": True, "enabled": True}
    with pytest.raises(HTTPException, match="missing model glm"):
        ManagementRuntime.gateway_configuration(None, enabled, {})


def test_migration_and_copy_keep_private_resources_isolated(store):
    revision, data = store.read()
    assert len(data["agents"]) == 2 and len(data["resources"]) == 2
    store.save_agent("copy-agent", {}, revision, source="agent-code")
    _, changed = store.read()
    copied = changed["agents"]["copy-agent"]
    assert copied["active"] is None and copied["versions"] == []
    binding = copied["draft"]["bindings"][0]
    assert changed["resources"][binding["id"]]["owner"] == "copy-agent"
    assert (
        binding["id"] != changed["agents"]["agent-code"]["draft"]["bindings"][0]["id"]
    )


def test_revisions_and_model_reference_protection(store):
    revision, data = store.read()
    model = dict(data["models"]["glm"], enabled=False)
    with pytest.raises(HTTPException, match="referenced"):
        store.save_model("glm", model, revision)
    model = {
        "id": "new-model",
        "name": "New",
        "provider": "openai-compatible",
        "api_key": "secret",
        "upstream_model": "example",
        "base_url": "https://provider.example/v1",
    }
    store.save_model("new-model", model, revision)
    with pytest.raises(HTTPException) as error:
        store.save_model("new-model", model, revision)
    assert error.value.status_code == 409
    public = store.public_catalog()
    assert public["models"]["new-model"]["api_key"] != "secret"
    assert all(
        "new-model" not in a["draft"]["allowed_model_ids"]
        for a in public["agents"].values()
    )


def test_resources_pin_versions_and_reject_cross_agent_reference(store):
    store.upload_skill("global-skill", "SKILL.md", SKILL)
    _, d = store.read()
    store.publish_resource("global-skill", d["resources"]["global-skill"]["draft"])
    _, d = store.read()
    cfg = copy.deepcopy(d["agents"]["agent-code"]["draft"])
    cfg["bindings"].append({"id": "global-skill", "version": 1})
    store.save_agent("agent-code", cfg)
    store.upload_skill("global-skill", "SKILL.md", SKILL + b" New version")
    _, d = store.read()
    store.publish_resource("global-skill", d["resources"]["global-skill"]["draft"])
    _, d = store.read()
    assert d["agents"]["agent-code"]["draft"]["bindings"][-1]["version"] == 1
    cfg["bindings"].append(d["agents"]["agent-data"]["draft"]["bindings"][0])
    with pytest.raises(HTTPException, match="private"):
        store.save_agent("agent-code", cfg)


def make_zip(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return output.getvalue()


@pytest.mark.parametrize(
    "name",
    [
        "../SKILL.md",
        "/SKILL.md",
        "C:/SKILL.md",
        "folder/../SKILL.md",
        "folder\\SKILL.md",
    ],
)
def test_skill_archive_cannot_escape(name):
    archive = make_zip([(name.replace("\\", "/"), SKILL)])
    if "\\" in name:
        archive = archive.replace(name.replace("\\", "/").encode(), name.encode())
    with pytest.raises(HTTPException):
        unpack_skill("skill.zip", archive)


def test_skill_zip_requires_one_root_and_rejects_links():
    meta, files = unpack_skill(
        "skill.zip",
        make_zip([("sample/SKILL.md", SKILL), ("sample/scripts/test.py", b"print(1)")]),
    )
    assert meta["name"] == "sample" and "scripts/test.py" in files
    with pytest.raises(HTTPException):
        unpack_skill(
            "skill.zip", make_zip([("one/SKILL.md", SKILL), ("two/SKILL.md", SKILL)])
        )
    entry = zipfile.ZipInfo("SKILL.md")
    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(HTTPException):
        unpack_skill("skill.zip", make_zip([(entry, SKILL)]))


def test_mcp_form_does_not_enable_oauth_or_install_packages():
    remote = validate_mcp(
        {
            "type": "remote",
            "url": "https://mcp.example",
            "headers": {"Authorization": "secret"},
        }
    )
    assert remote["oauth"] is False
    assert redact(remote)["headers"]["Authorization"] != "secret"
    with pytest.raises(HTTPException):
        validate_mcp({"type": "local", "command": ["npx", "something"]})
    with pytest.raises(HTTPException):
        validate_mcp({"type": "remote", "url": "https://mcp.example", "oauth": {}})


def test_managed_model_validation_and_native_config_write(store):
    runtime = object.__new__(ManagementRuntime)
    runtime.store, runtime.blocked = store, set()
    assert runtime.authorize("agent-code", "POST", "session", {})
    with pytest.raises(HTTPException) as e:
        runtime.authorize(
            "agent-code",
            "POST",
            "session/ses_x/prompt_async",
            {"model": {"providerID": "cloud-model-gateway", "modelID": "minimax"}},
        )
    assert e.value.status_code == 403
    with pytest.raises(HTTPException):
        runtime.authorize("agent-code", "PATCH", "config", {})


def test_effective_config_uses_skill_discovery_and_preserves_trace(store):
    config = SimpleNamespace(
        sandbox=SimpleNamespace(
            image="sha256:" + "a" * 64,
            idle_timeout_seconds=1800,
            default_cpu=4,
            default_memory_mb=4096,
            default_pids=512,
        ),
        model_gateway=SimpleNamespace(base_url="http://127.0.0.1:4001/v1"),
    )
    runtime = object.__new__(ManagementRuntime)
    runtime.store, runtime.backend = store, SimpleNamespace(config=config)
    _, data = store.read()
    before = set(store.root.rglob("*"))
    preview = runtime.compile_agent(
        data, "agent-code", data["agents"]["agent-code"]["draft"], 0, preview=True
    )
    assert set(store.root.rglob("*")) == before
    path = runtime.compile_agent(
        data, "agent-code", data["agents"]["agent-code"]["draft"], 2
    )
    cfg = json.loads((path / "opencode.json").read_text())
    assert preview["opencode"] == redact(cfg)
    assert cfg["skills"]["paths"] == ["/opt/agent/skills"]
    assert cfg["instructions"] == ["/opt/agent/AGENTS.md"]
    assert cfg["plugin"][0].endswith("/system-trace.mjs")
    system_trace = (path / "plugins/system-trace.mjs").read_text()
    assert '"chat.headers"' in system_trace
    assert "^msg_([0-9a-f]{32})$" in system_trace
    assert "output.headers.traceparent" in system_trace
    assert set(cfg["provider"]["cloud-model-gateway"]["models"]) == {
        "glm",
    }


def test_configuration_previews_are_read_only_and_mask_gateway_headers(store):
    runtime = object.__new__(ManagementRuntime)
    runtime.store = store
    runtime.backend = SimpleNamespace(
        config=SimpleNamespace(
            sandbox=SimpleNamespace(default_cpu=4, default_memory_mb=4096, default_pids=512),
            model_gateway=SimpleNamespace(base_url="http://127.0.0.1:4001/v1")
        )
    )
    app = FastAPI()
    app.include_router(create_admin_router(store, runtime))
    gateway = store.root / "gateway/config.json"
    gateway.parent.mkdir(exist_ok=True)
    gateway.write_text(
        json.dumps(
            {
                "model_list": [
                    {
                        "litellm_params": {
                            "api_key": "private-key",
                            "extra_headers": {"Authorization": "private-header"},
                        }
                    }
                ]
            }
        )
    )
    revision, data = store.read()
    with TestClient(app) as client:
        result = client.get("/cloud/admin/config-preview")
        assert result.status_code == 200
        assert "private-key" not in result.text and "private-header" not in result.text
        assert all(
            not resource.get("owner")
            for resource in result.json()["resources"].values()
        )
        before = set(store.root.rglob("*"))
        response = client.post(
            "/cloud/admin/agents/agent-code/config-preview",
            json={"config": data["agents"]["agent-code"]["draft"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["opencode"]["model"].startswith("cloud-model-gateway/")
        assert set(store.root.rglob("*")) == before and store.read()[0] == revision
        active = client.get("/cloud/admin/agents/agent-code/effective-config")
        assert active.status_code == 200, active.text
        assert "active_opencode" in active.json() and "draft_opencode" in active.json()
