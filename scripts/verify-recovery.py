#!/usr/bin/env python3
"""Crash/restart the actual controller process with private Docker sandboxes."""
import asyncio
import configparser
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import docker
import httpx
from app.registry import Registry

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = "stage31-recovery"


async def main():
    report = {"result": "running"}
    client = docker.from_env()
    process = None
    cleanup_errors = []
    with tempfile.TemporaryDirectory(prefix="cloud-recovery-") as temporary:
        directory = Path(temporary)
        shutil.copytree(ROOT / "agents", directory / "agents")
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(ROOT / "config.cfg")
        parser["platform"]["instance_id"] = INSTANCE
        parser["platform"]["data_root"] = str(directory)
        parser["storage"]["workspace_root"] = str(directory / "workspaces")
        parser["storage"]["state_root"] = str(directory / "state")
        parser["storage"]["max_user_workspace_gb"] = "1"
        with (directory / "config.cfg").open("w") as handle:
            parser.write(handle)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP) as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        log = (directory / "controller.log").open("wb")
        async with httpx.AsyncClient(base_url=base, trust_env=False, timeout=30) as api:
            async def start():
                nonlocal process
                process = subprocess.Popen([sys.executable, "-m", "app.main", "--config", str(directory / "config.cfg"),
                    "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, stdout=log, stderr=log)
                for _ in range(200):
                    if process.poll() is not None:
                        raise RuntimeError("controller process exited during startup")
                    try:
                        if (await api.get("/cloud/health/ready", timeout=1)).status_code == 200:
                            return
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.1)
                raise RuntimeError("controller readiness timeout")

            async def stop(crash=False):
                if process and process.poll() is None:
                    process.kill() if crash else process.terminate()
                    await asyncio.to_thread(process.wait, timeout=20)

            async def session(username):
                response = await api.post("/session", json={"_cloud": {"agent_id": "agent-code", "username": username}})
                response.raise_for_status()
                return response.json()["id"]

            try:
                await start()
                alice = await session("recovery-alice")
                bob = await session("recovery-bob")
                registry = Registry(directory / "platform.db")
                a = registry.get_sandbox("agent-code", "recovery-alice")
                b = registry.get_sandbox("agent-code", "recovery-bob")
                marker = directory / "workspaces/agent-code/recovery-alice/shared/keep.txt"
                marker.write_bytes(b"preserved")
                # Kill an idle OpenCode container; route and native session must survive restart.
                await asyncio.to_thread(client.containers.get(a.container_id).kill)
                resumed = await api.get(f"/session/{alice}")
                resumed.raise_for_status()
                assert resumed.json()["id"] == alice
                report["idle_sandbox_kill_recovered"] = True
                # SIGKILL skips lifespan shutdown, exercising actual process crash/WAL recovery.
                await stop(crash=True)
                a = registry.get_sandbox("agent-code", "recovery-alice")
                assert client.containers.get(a.container_id).status == "running"
                await asyncio.to_thread(client.containers.get(b.container_id).remove, force=True)
                registry.upsert_sandbox(sandbox_id=a.sandbox_id, agent_id=a.agent_id, username=a.username,
                    container_id="stale-controller-record", host_port=1, status="unhealthy",
                    image_version=a.image_version, last_active_at=a.last_active_at)
                await start()
                recovered = registry.get_sandbox(a.agent_id, a.username)
                assert recovered.container_id == a.container_id and recovered.status == "ready"
                assert registry.get_sandbox(b.agent_id, b.username).status == "missing"
                assert (await api.get(f"/session/{alice}")).json()["id"] == alice
                assert (await api.get(f"/session/{bob}")).json()["id"] == bob
                assert registry.get_sandbox(b.agent_id, b.username).container_id != b.container_id
                assert marker.read_bytes() == b"preserved"
                report["controller_sigkill_recovery"] = {"same_running_container": True, "stale_record_repaired": True,
                    "missing_marked_and_recreated": True, "old_sessions_resolved": 2}
                # A sparse quota fixture consumes logical quota without filling the host disk.
                occupancy = marker.parent / "quota-fixture.bin"
                with occupancy.open("wb") as handle:
                    handle.truncate(1024**3)
                rejected = await api.post("/cloud/files/upload", data={"agent_id": a.agent_id, "username": a.username,
                    "relative_path": "keep.txt"}, files={"file": ("keep.txt", b"x" * 2048)})
                assert rejected.status_code == 413 and "quota" in rejected.text.lower()
                assert marker.read_bytes() == b"preserved"
                assert not list(marker.parent.glob(".upload-*.tmp"))
                report["quota"] = {"http_status": 413, "existing_file_intact": True,
                    "fixture_logical_bytes": occupancy.stat().st_size, "fixture_allocated_bytes": occupancy.stat().st_blocks * 512}
                occupancy.unlink()
                with registry.connect() as connection:
                    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                report["result"] = "passed"
            except Exception as exc:
                report.update(result="failed", error=f"{type(exc).__name__}: {exc}")
            finally:
                try:
                    await stop()
                except Exception as exc:
                    cleanup_errors.append(type(exc).__name__)
                    if process and process.poll() is None:
                        process.kill()
                        await asyncio.to_thread(process.wait)
                log.close()
                for container in client.containers.list(all=True, filters={"label": f"cloud.platform_instance={INSTANCE}"}):
                    try:
                        assert container.labels.get("cloud.platform_instance") == INSTANCE
                        await asyncio.to_thread(container.remove, force=True)
                    except Exception as exc:
                        cleanup_errors.append(type(exc).__name__)
                if client.containers.list(all=True, filters={"label": f"cloud.platform_instance={INSTANCE}"}):
                    cleanup_errors.append("containers remain")
    client.close()
    if cleanup_errors:
        report.update(result="failed", cleanup_errors=cleanup_errors)
    destination = ROOT / "artifacts/recovery/report.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return report["result"] != "passed"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
