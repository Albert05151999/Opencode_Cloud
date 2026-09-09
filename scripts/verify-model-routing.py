#!/usr/bin/env python3
"""Verify native model selection through real OpenCode and LiteLLM containers."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

import docker
import httpx

from app.config import load_config
from app.gateway import create_gateway_router
from app.main import create_app
from app.registry import Registry
from app.sandbox import LocalDockerBackend
from app.workspace import WorkspaceManager

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/model-routing/report.json"
INSTANCE = "stage19-verification"


async def verify_opencode(state) -> None:
    client = docker.from_env()
    report: dict = {"result": "running", "requests": []}
    with tempfile.TemporaryDirectory(prefix="cloud-stage19-") as temporary:
        directory = Path(temporary)
        shutil.copytree(ROOT / "agents", directory / "agents")
        config = load_config(ROOT / "config.cfg")
        config = replace(config, platform=replace(config.platform, instance_id=INSTANCE))
        registry = Registry(directory / "registry.db")
        registry.initialize()
        backend = LocalDockerBackend(
            config, registry,
            WorkspaceManager(directory / "workspaces", directory / "state", runtime_uid=10001, runtime_gid=10001),
            directory / "agents", client=client,
        )
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=60) as upstream:
                app = create_app(create_gateway_router(registry, backend, upstream))
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://gateway.test") as gateway:
                    for agent, models in [("agent-code", ["coding-fast", "coding-quality"]), ("agent-data", ["data-fast", "data-quality"])]:
                        for model in models:
                            marker = f"stage19-{agent}-{model}"
                            response = await gateway.post("/session", json={"_cloud": {"agent_id": agent, "username": "alice"}, "title": marker})
                            assert response.is_success, response.text
                            session_id = response.json()["id"]
                            before = len(state.traces)
                            response = await gateway.post(
                                f"/session/{session_id}/message",
                                json={"model": {"providerID": "cloud-model-gateway", "modelID": model}, "parts": [{"type": "text", "text": marker}]},
                            )
                            assert response.is_success, response.text
                            payload = response.json()
                            assert not payload.get("info", {}).get("error"), payload
                            text = "".join(part.get("text", "") for part in payload.get("parts", []) if part.get("type") == "text")
                            assert text in {"backend-a", "backend-b"}, payload
                            traces = state.traces[before:]
                            matching = [trace for trace in traces if marker in json.dumps(trace.get("messages"))]
                            assert matching, traces
                            assert all(trace["stream"] is True and trace["model"] == "mock-model" for trace in matching)
                            info = payload["info"]
                            assert info["providerID"] == "cloud-model-gateway" and info["modelID"] == model, info
                            report["requests"].append({"agent": agent, "logical_model": model, "session_id": session_id, "backend": text, "backend_request_count": len(matching), "native_model": {"providerID": info["providerID"], "modelID": info["modelID"]}})
            report["result"] = "passed"
            report["scope"] = "Real gateway routing, OpenCode and LiteLLM; deterministic local model responses."
        except Exception as exc:
            report["result"] = "failed"
            report["error"] = str(exc)
            raise
        finally:
            REPORT.parent.mkdir(parents=True, exist_ok=True)
            for container in client.containers.list(all=True, filters={"label": f"cloud.platform_instance={INSTANCE}"}):
                if container.labels.get("cloud.platform_instance") != INSTANCE:
                    raise RuntimeError("container ownership mismatch")
                (REPORT.parent / f"{container.labels['cloud.agent_id']}.log").write_bytes(container.logs(tail=200))
                container.remove(force=True)
            REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


async def main() -> None:
    spec = importlib.util.spec_from_file_location("litellm_verification", ROOT / "scripts/verify-litellm.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    await module.verify(integration_hook=verify_opencode, gateway_port=4001)
    print(REPORT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    asyncio.run(main())
