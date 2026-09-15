import configparser
import copy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from catalog_service.src.admin_dto import AgentDefinition
from catalog_service.src.compiler import Compiler
from test.catalog_service.unit.test_catalog_management import store


@pytest.mark.parametrize("cpu", [1, 2, 4, 8, None])
@pytest.mark.parametrize("memory", [1024, 2048, 4096, 8192, None])
def test_resources_survive_save_copy_and_compile(store, cpu, memory):
    _, data = store.read()
    cfg = copy.deepcopy(data["agents"]["agent-code"]["draft"])
    cfg.update(cpu_limit=cpu, memory_mb=memory)
    cfg = AgentDefinition.model_validate(cfg).model_dump()
    store.save_agent("agent-code", cfg)
    store.save_agent("copy-agent", {}, source="agent-code")
    _, data = store.read()
    copied = data["agents"]["copy-agent"]["draft"]
    assert copied["cpu_limit"] == cpu and copied["memory_mb"] == memory
    runtime = Compiler(store, SimpleNamespace(
        sandbox=SimpleNamespace(default_cpu=4, default_memory_mb=4096,
            default_pids=512, image="sha256:" + "a" * 64, idle_timeout_seconds=1800),
        model_gateway=SimpleNamespace(base_url="http://gateway:8104/v1"),
    ))
    preview = runtime.compile_agent(data, "copy-agent", copied, 1, preview=True)
    path = runtime.compile_agent(data, "copy-agent", copied, 1)
    ini = configparser.ConfigParser()
    ini.read(path / "agent.cfg")
    assert ini.getfloat("resources", "cpu_limit") == (cpu or 4)
    assert ini.getint("resources", "memory_mb") == (memory or 4096)
    assert preview["resources"]["cpu_limit"] == (cpu or 4)
    assert preview["resources"]["memory_mb"] == (memory or 4096)


@pytest.mark.parametrize("field,value", [
    ("cpu_limit", 0), ("cpu_limit", 3), ("cpu_limit", 16),
    ("cpu_limit", True), ("cpu_limit", 1.0), ("cpu_limit", "2"),
    ("memory_mb", 1), ("memory_mb", 3072), ("memory_mb", -1024),
    ("memory_mb", 16384), ("memory_mb", True), ("memory_mb", "1024"),
])
def test_invalid_resources_rejected_in_schema_and_store(store, field, value):
    _, data = store.read()
    cfg = copy.deepcopy(data["agents"]["agent-code"]["draft"])
    cfg[field] = value
    with pytest.raises(ValidationError):
        AgentDefinition.model_validate(cfg)
    with pytest.raises(HTTPException, match=field):
        store.save_agent("agent-code", cfg)
