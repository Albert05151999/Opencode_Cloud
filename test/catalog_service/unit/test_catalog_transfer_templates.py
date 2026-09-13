import copy
import json

import pytest
from fastapi import HTTPException

from catalog_service.src.agent_templates import AgentTemplates
from test.catalog_service.unit.test_catalog_transfers import service, choices, SKILL


@pytest.mark.parametrize("template", [{}, {"id": "bad", "config": {}}, None])
def test_invalid_template_is_rejected_without_staging(service, template):
    payload = json.loads(service.export())
    payload["agent_templates"] = [template]
    with pytest.raises(HTTPException) as error:
        service.preview("transfer.json", json.dumps(payload).encode())
    assert error.value.status_code == 400
    with service.store.connect() as db:
        assert db.execute("SELECT count(*) FROM resource_imports").fetchone()[0] == 0


def test_migration_keeps_fixed_versions_and_templates_separate(service):
    store = service.store
    store.upload_skill("versioned", "SKILL.md", SKILL)
    store.publish_resource(
        "versioned", copy.deepcopy(store.read()[1]["resources"]["versioned"]["draft"])
    )
    cfg = copy.deepcopy(store.read()[1]["agents"]["agent-code"]["draft"])
    cfg["bindings"] = [{"id": "versioned", "version": 1}]
    store.save_agent("source", cfg)
    store.upload_skill("versioned", "SKILL.md", SKILL + b"\nVersion two")
    store.publish_resource(
        "versioned", copy.deepcopy(store.read()[1]["resources"]["versioned"]["draft"])
    )
    before = copy.deepcopy(store.read()[1]["agents"])
    preview = service.preview("transfer.json", service.export())
    result = service.commit(preview["preview_id"], choices(preview, "-copy"))
    assert store.read()[1]["agents"] == before
    template = next(
        t for t in AgentTemplates(store).list() if t["source_id"] == "source-draft"
    )
    binding = template["config"]["bindings"][0]
    with pytest.raises(HTTPException):
        AgentTemplates(store).restore(template["id"], "restored")
    resource = store.read()[1]["resources"][binding["id"]]
    assert store.file(resource["draft"]["files"]["SKILL.md"]) == SKILL
    store.publish_resource(resource["id"], copy.deepcopy(resource["draft"]))
    AgentTemplates(store).restore(template["id"], "restored")
    restored = store.read()[1]["agents"]["restored"]
    assert (
        restored["active"] is None and restored["draft"]["bindings"][0]["version"] == 1
    )
    assert result["agent_templates"]


def test_resource_file_checksum_blocks_tampered_import(service):
    payload = json.loads(service.export())
    entry = next(i for i in payload["items"] if i.get("file_sha256"))
    key = next(iter(entry["file_sha256"]))
    entry["file_sha256"][key] = "0" * 64
    preview = service.preview("transfer.json", json.dumps(payload).encode())
    assert any(
        i.get("error") == "Resource file checksum mismatch" for i in preview["items"]
    )


def test_legacy_models_export_as_managed_models_with_both_routes(service):
    from types import SimpleNamespace
    from catalog_service.src.compiler import Compiler as ManagementRuntime

    env = {}
    for mid in service.store.read()[1]["models"]:
        prefix = mid.upper().replace("-", "_")
        env.update(
            {
                prefix + "_MODEL": "openai/upstream",
                prefix + "_API_KEY": "legacy-key",
                prefix + "_1_API_BASE": "https://one.example/v1",
                prefix + "_2_API_BASE": "https://two.example/v1",
            }
        )
    service.runtime = SimpleNamespace(gateway_environment=lambda: env)
    manifest = json.loads(service.export(True))
    model = next(i["data"] for i in manifest["items"] if i["kind"] == "model")
    assert model["api_key"] == "legacy-key" and model["provider"] == "openai-compatible"
    model["enabled"] = True
    compiled = ManagementRuntime.gateway_configuration(None, {model["id"]: model}, {})
    assert [i["litellm_params"]["api_base"] for i in compiled["model_list"]] == [
        "https://one.example/v1",
        "https://two.example/v1",
    ]
