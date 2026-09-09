#!/usr/bin/env python3
"""Compare Docker PID 1 behavior using the pinned runtime, without model calls."""
import asyncio
import json
import shutil
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from app.config import load_config
from app.main import build_app

ROOT = Path(__file__).resolve().parents[1]


async def main():
    results = []
    with tempfile.TemporaryDirectory(prefix="cloud-stop-probe-") as temporary:
        directory = Path(temporary)
        shutil.copytree(ROOT / "agents", directory / "agents")
        config = load_config(ROOT / "config.cfg")
        config = replace(config, platform=replace(config.platform, instance_id="stop-probe", data_root=str(directory)),
                         storage=replace(config.storage, workspace_root=str(directory / "workspaces"), state_root=str(directory / "state")))
        app = build_app(config, directory / "agents")
        backend = app.state.backend
        docker_client = backend.client
        containers = docker_client.containers
        create = containers.create
        backend.client = SimpleNamespace(containers=containers, images=docker_client.images, close=docker_client.close)
        try:
            for use_init in (False, True):
                def configured_create(**kwargs):
                    kwargs["init"] = use_init
                    return create(**kwargs)
                backend.client.containers.create = configured_create
                endpoint = await backend.acquire("agent-code", f"stop-{str(use_init).lower()}")
                await backend.release(endpoint)
                container = backend.client.containers.get(endpoint.container_id)
                command = container.exec_run(["cat", "/proc/1/comm"]).output.decode().strip()
                assert bool(container.attrs["HostConfig"].get("Init")) == use_init
                started = time.perf_counter()
                await asyncio.to_thread(container.stop, timeout=10)
                elapsed = time.perf_counter() - started
                container.reload()
                results.append({"init": use_init, "pid1": command, "stop_seconds": elapsed,
                                "exit_code": container.attrs["State"]["ExitCode"],
                                "oom_killed": container.attrs["State"]["OOMKilled"]})
                await asyncio.to_thread(container.remove)
        finally:
            for container in backend.client.containers.list(all=True, filters={"label": "cloud.platform_instance=stop-probe"}):
                assert container.labels.get("cloud.platform_instance") == "stop-probe"
                container.remove(force=True)
            await app.state.health_monitor.client.aclose()
            backend.client.close()
    report = {"result": "passed" if all(not item["oom_killed"] for item in results) and len(results) == 2 else "failed", "samples": results}
    path = ROOT / "artifacts/perf/container-stop.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
