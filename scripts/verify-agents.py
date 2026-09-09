#!/usr/bin/env python3
"""Verify the two repository Agent definitions in real isolated sandboxes."""

from __future__ import annotations

import asyncio
import atexit
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import docker
import httpx

from app.agents import AgentCatalog
from app.config import load_config
from app.registry import Registry
from app.sandbox import LocalDockerBackend
from app.workspace import WorkspaceManager


PROJECT = Path(__file__).resolve().parents[1]
TEST_ROOT = Path("/tmp/cloud-agent-stage17-verification")
REPORT = PROJECT / "artifacts" / "agents" / "report.json"
INSTANCE = "stage17-verification"
EXPECTED = {
    "agent-code": {
        "default": "coding-fast",
        "models": {"coding-fast", "coding-quality"},
        "skill": "skills/repo-analysis/SKILL.md",
        "agent_text": "Analyze repositories",
        "skill_text": "Inspect a repository",
    },
    "agent-data": {
        "default": "data-fast",
        "models": {"data-fast", "data-quality"},
        "skill": "skills/spreadsheet-analysis/SKILL.md",
        "agent_text": "Python data and office libraries",
        "skill_text": "Analyze and generate validated spreadsheet artifacts",
    },
}


def remove_instance_containers(client: docker.DockerClient) -> None:
    filters = {"label": f"cloud.platform_instance={INSTANCE}"}
    for container in client.containers.list(all=True, filters=filters):
        container.reload()
        labels = container.attrs.get("Config", {}).get("Labels") or {}
        if labels.get("cloud.platform_instance") != INSTANCE:
            raise RuntimeError(f"refusing to remove non-{INSTANCE} container {container.id}")
        container.remove(force=True)


def remove_test_root() -> None:
    if not TEST_ROOT.exists():
        return
    resolved = TEST_ROOT.resolve(strict=True)
    if resolved != TEST_ROOT:
        raise RuntimeError(f"refusing to remove unexpected test root {resolved}")
    shutil.rmtree(resolved)


def parse_definitions() -> dict[str, dict[str, Any]]:
    parsed: dict[str, dict[str, Any]] = {}
    catalog = AgentCatalog(PROJECT / "agents")
    definitions = catalog.load_all()
    assert set(definitions) == set(EXPECTED)
    for agent_id, expected in EXPECTED.items():
        agent = definitions[agent_id]
        root = agent.path
        definition = agent.opencode
        allowed = set(agent.allowed_models)
        assert agent.default_model == expected["default"]
        assert allowed == expected["models"]
        assert definition["model"] == f"cloud-model-gateway/{expected['default']}"
        provider = definition["provider"]["cloud-model-gateway"]
        assert set(provider["models"]) == expected["models"]
        assert provider["options"]["baseURL"] == "http://host.docker.internal:4001/v1"
        assert definition["enabled_providers"] == ["cloud-model-gateway"]
        assert expected["agent_text"] in (root / "AGENTS.md").read_text(encoding="utf-8")
        assert expected["skill_text"] in (root / expected["skill"]).read_text(encoding="utf-8")
        parsed[agent_id] = {
            "image": agent.image,
            "default_model": expected["default"],
            "allowed_models": sorted(allowed),
            "provider_base_url": provider["options"]["baseURL"],
        }
    return parsed


def config_models(payload: dict[str, Any]) -> tuple[str, set[str]]:
    default = payload.get("model")
    provider = payload.get("provider", {}).get("cloud-model-gateway", {})
    models = set(provider.get("models", {}))
    assert isinstance(default, str)
    return default, models


async def verify() -> dict[str, Any]:
    definitions = parse_definitions()
    assert definitions["agent-code"]["image"] == definitions["agent-data"]["image"]

    docker_client = docker.from_env()
    docker_client.ping()
    remove_instance_containers(docker_client)
    remove_test_root()
    TEST_ROOT.mkdir(parents=True)
    shutil.copytree(PROJECT / "agents", TEST_ROOT / "agents")

    def cleanup() -> None:
        remove_instance_containers(docker_client)
        remove_test_root()

    atexit.register(cleanup)
    config = load_config(PROJECT / "config.cfg")
    config = replace(config, platform=replace(config.platform, instance_id=INSTANCE))
    assert config.sandbox.image == definitions["agent-code"]["image"]
    registry = Registry(TEST_ROOT / "platform.db")
    registry.initialize()
    workspaces = WorkspaceManager(
        TEST_ROOT / "workspaces", TEST_ROOT / "state",
        runtime_uid=10001, runtime_gid=10001,
    )
    manager = LocalDockerBackend(
        config, registry, workspaces, TEST_ROOT / "agents", client=docker_client
    )
    code_endpoint, data_endpoint = await asyncio.gather(
        manager.acquire("agent-code", "alice"),
        manager.acquire("agent-data", "alice"),
    )
    assert code_endpoint.container_id != data_endpoint.container_id

    containers = {
        "agent-code": docker_client.containers.get(code_endpoint.container_id),
        "agent-data": docker_client.containers.get(data_endpoint.container_id),
    }
    image_refs: dict[str, str] = {}
    image_ids: dict[str, str] = {}
    mounts_report: dict[str, dict[str, object]] = {}
    health_report: dict[str, dict[str, object]] = {}
    config_report: dict[str, dict[str, object]] = {}
    logs: dict[str, str] = {}

    async with httpx.AsyncClient(trust_env=False, timeout=10) as http:
        for agent_id, container in containers.items():
            await asyncio.to_thread(container.reload)
            image_refs[agent_id] = container.attrs["Config"]["Image"]
            image_ids[agent_id] = container.image.id
            mounts = {item["Destination"]: item for item in container.attrs["Mounts"]}
            agent_mount = mounts["/opt/agent"]
            expected_source = str((TEST_ROOT / "agents" / agent_id).resolve())
            assert agent_mount["Source"] == expected_source
            assert agent_mount["RW"] is False
            assert all(
                item["Source"] != str((TEST_ROOT / "agents" / other).resolve())
                for other in EXPECTED if other != agent_id
                for item in mounts.values()
            )
            mounts_report[agent_id] = {
                "source": agent_mount["Source"], "destination": "/opt/agent", "read_only": True,
            }

            health = await http.get(f"http://127.0.0.1:{code_endpoint.host_port if agent_id == 'agent-code' else data_endpoint.host_port}/global/health")
            health.raise_for_status()
            health_payload = health.json()
            assert health_payload == {"healthy": True, "version": config.opencode.expected_version}
            health_report[agent_id] = health_payload

            effective = await http.get(f"http://127.0.0.1:{code_endpoint.host_port if agent_id == 'agent-code' else data_endpoint.host_port}/config")
            effective.raise_for_status()
            effective_payload = effective.json()
            default, models = config_models(effective_payload)
            expected = EXPECTED[agent_id]
            assert default == f"cloud-model-gateway/{expected['default']}"
            assert models == expected["models"]
            config_report[agent_id] = {
                "default_model": default,
                "logical_models": sorted(models),
                "enabled_providers": effective_payload.get("enabled_providers"),
            }

            agent_text = await asyncio.to_thread(
                container.exec_run, ["cat", "/opt/agent/AGENTS.md"]
            )
            skill_text = await asyncio.to_thread(
                container.exec_run, ["cat", f"/opt/agent/{expected['skill']}"]
            )
            assert agent_text.exit_code == 0 and expected["agent_text"].encode() in agent_text.output
            assert skill_text.exit_code == 0 and expected["skill_text"].encode() in skill_text.output
            logs[agent_id] = container.logs(tail=100).decode(errors="replace")

    assert len(set(image_refs.values())) == 1
    assert len(set(image_ids.values())) == 1
    assert next(iter(image_refs.values())) == definitions["agent-code"]["image"]
    assert next(iter(image_ids.values())) == definitions["agent-code"]["image"]

    dynamic_install_observed = {
        agent_id: "install" in text.lower() or "download" in text.lower()
        for agent_id, text in logs.items()
    }
    report = {
        "result": "passed",
        "instance_id": INSTANCE,
        "container_ids": {
            "agent-code": code_endpoint.container_id,
            "agent-data": data_endpoint.container_id,
        },
        "config_image": definitions["agent-code"]["image"],
        "container_config_image": image_refs,
        "resolved_image_content_id": image_ids,
        "mounts": mounts_report,
        "health": health_report,
        "effective_config": config_report,
        "definition_summary": definitions,
        "startup_log_mentions_install_or_download": dynamic_install_observed,
        "checks": [
            "repository Agent definitions parsed and matched their declared model policies",
            "agent-code x alice and agent-data x alice used distinct containers",
            "both containers used the same exact image content ID",
            "each /opt/agent mounted only its matching definition read-only",
            "effective /config exposed only each Agent's logical models and default",
            "both health endpoints reported the pinned OpenCode version",
            "each container could read its matching AGENTS.md and skill text",
            "no real model request was sent",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    cleanup()
    atexit.unregister(cleanup)
    return report


if __name__ == "__main__":
    print(json.dumps(asyncio.run(verify()), indent=2))
