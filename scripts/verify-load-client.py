#!/usr/bin/env python3
"""Verify the load client against real HTTP, SSE, Docker and local model fixtures."""
import asyncio
import importlib.util
import json
import shutil
import socket
import tempfile
from dataclasses import replace
from pathlib import Path

import uvicorn

from app.config import load_config
from app.main import build_app

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = "stage26-verification"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


async def verify_client(state):
    load = module("cloud_load_client", "tests/load/run_load.py")
    with tempfile.TemporaryDirectory(prefix="cloud-stage26-") as temporary:
        directory = Path(temporary)
        shutil.copytree(ROOT / "agents", directory / "agents")
        config = load_config(ROOT / "config.cfg")
        config = replace(config, platform=replace(config.platform, instance_id=INSTANCE, data_root=str(directory)), storage=replace(config.storage, workspace_root=str(directory / "workspaces"), state_root=str(directory / "state")))
        app = build_app(config, directory / "agents")
        backend = app.state.backend
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(15):
                while not server.started:
                    if task.done():
                        await task
                    await asyncio.sleep(0.05)
            result = await load.run(f"http://127.0.0.1:{listener.getsockname()[1]}", rounds=1, output=ROOT / "artifacts/perf/load-client-smoke", timeout=60)
            assert result["request_count"] == 8 and result["failures"] == 0, result
            async with asyncio.timeout(10):
                while backend.in_use:
                    await asyncio.sleep(0.05)
            report = {"result": "passed", "scope": "Load-client correctness only; local mock model, not final performance acceptance", "requests": 8, "leases_after_disconnect": 0, "summary": result}
            (ROOT / "artifacts/perf/load-client-verification.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2))
        finally:
            for container in backend.client.containers.list(all=True, filters={"label": f"cloud.platform_instance={INSTANCE}"}):
                if container.labels.get("cloud.platform_instance") != INSTANCE:
                    raise RuntimeError("container ownership mismatch")
                container.remove(force=True)
            server.should_exit = True
            await task
            listener.close()


if __name__ == "__main__":
    fixture = module("litellm_fixture", "scripts/verify-litellm.py")
    asyncio.run(fixture.verify(integration_hook=verify_client, gateway_port=4001))
