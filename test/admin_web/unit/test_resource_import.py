import base64
import json

import pytest
from fastapi import HTTPException

from admin_web.local_service.importer import Importer
from admin_web.local_service.resource_import import collect


def test_explicit_config_does_not_merge_other_discovered_files(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "other"))
    (tmp_path / "other/opencode").mkdir(parents=True)
    (tmp_path / "other/opencode/opencode.json").write_text("{}")
    config = tmp_path / "opencode.json"
    config.write_text(
        '{"mcp":{"docs":{"type":"remote","url":"https://example.org/mcp"}}}'
    )
    skill = tmp_path / "skills/demo"
    skill.mkdir(parents=True)
    raw = b"---\nname: demo\ndescription: Test skill\n---\nRead me."
    (skill / "SKILL.md").write_bytes(raw)
    result = json.loads(collect(Importer(tmp_path), str(config)))
    assert {item["kind"] for item in result["items"]} == {"mcp", "skill"}
    entry = next(item for item in result["items"] if item["kind"] == "skill")
    assert base64.b64decode(entry["files"]["SKILL.md"]) == raw


def test_external_skill_requires_explicit_selection(tmp_path):
    (tmp_path / "project").mkdir()
    (tmp_path / "external").mkdir()
    (tmp_path / "external/SKILL.md").write_text(
        "---\nname: external\ndescription: External\n---\nBody"
    )
    config = tmp_path / "project/opencode.json"
    config.write_text('{"skills":{"paths":["../external"]}}')
    with pytest.raises(HTTPException):
        collect(Importer(tmp_path), str(config))
    assert len(json.loads(collect(Importer(tmp_path), str(config), True))["items"]) == 1
