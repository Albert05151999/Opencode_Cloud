#!/usr/bin/env python3
"""Observe first project initialization without exposing credentials or payloads."""
import asyncio
import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

import httpx
from app.config import load_config
from app.main import build_app

ROOT = Path(__file__).resolve().parents[1]


async def main():
    report = {"samples": []}
    with tempfile.TemporaryDirectory(prefix="cloud-init-probe-") as temporary:
        directory = Path(temporary)
        shutil.copytree(ROOT / "agents", directory / "agents")
        config = load_config(ROOT / "config.cfg")
        config = replace(config, platform=replace(config.platform, instance_id="init-probe", data_root=str(directory)),
                         storage=replace(config.storage, workspace_root=str(directory / "workspaces"), state_root=str(directory / "state")))
        app = build_app(config, directory / "agents")
        backend = app.state.backend
        try:
            endpoint = await backend.acquire("agent-code", "init-probe")
            await backend.release(endpoint)
            async with httpx.AsyncClient(trust_env=False, timeout=60) as api:
                response = await api.get(endpoint.base_url + "/session/status")
                report["status"] = response.status_code
            for elapsed in (0, 10, 20, 30):
                if elapsed:
                    await asyncio.sleep(10)
                files = [p for p in (directory / "state").rglob("*") if p.is_file() and not p.is_symlink()]
                largest = sorted(files, key=lambda p: p.stat().st_size, reverse=True)[:8]
                report["samples"].append({"elapsed_seconds": elapsed, "total_bytes": sum(p.stat().st_size for p in files),
                    "largest": [{"path": str(p.relative_to(directory)), "bytes": p.stat().st_size} for p in largest]})
            manifests = []
            for path in (directory / "state").rglob("package.json"):
                payload = json.loads(path.read_text())
                manifests.append({"path": str(path.relative_to(directory)), "name": payload.get("name"),
                                  "version": payload.get("version"), "dependencies": payload.get("dependencies")})
            report["package_manifests"] = manifests
            report["npm_index_keys"] = []
            for path in (directory / "state").rglob("*"):
                if path.is_file() and "index-v5" in path.parts:
                    for line in path.read_text(errors="replace").splitlines():
                        try:
                            key = json.loads(line.split("\t", 1)[1]).get("key", "")
                            if "registry.npmjs.org/" in key:
                                report["npm_index_keys"].append(key.split("?", 1)[0])
                        except (IndexError, ValueError):
                            pass
        finally:
            for container in backend.client.containers.list(all=True, filters={"label": "cloud.platform_instance=init-probe"}):
                assert container.labels.get("cloud.platform_instance") == "init-probe"
                container.remove(force=True)
            await app.state.health_monitor.client.aclose()
            backend.client.close()
    path = ROOT / "artifacts/perf/runtime-init-downloads.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
