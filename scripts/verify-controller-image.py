#!/usr/bin/env python3
"""Smoke-test a versioned controller image against its versioned runtime image."""
from __future__ import annotations

import argparse
import asyncio
import configparser
import json
import shutil
import socket
import tempfile
import uuid
from pathlib import Path
from typing import Any

import docker
import httpx

from app.registry import Registry


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts" / "release" / "controller-smoke.json"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def rewrite_fixture(directory: Path, instance: str, port: int, runtime_image: str) -> Path:
    shutil.copytree(ROOT / "agents", directory / "agents")
    for agent_cfg in (directory / "agents").glob("*/agent.cfg"):
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(agent_cfg)
        parser["agent"]["image"] = runtime_image
        with agent_cfg.open("w", encoding="utf-8") as handle:
            parser.write(handle)
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(ROOT / "config.cfg")
    parser["platform"]["instance_id"] = instance
    parser["platform"]["host"] = "127.0.0.1"
    parser["platform"]["port"] = str(port)
    parser["platform"]["data_root"] = str(directory)
    parser["sandbox"]["image"] = runtime_image
    parser["storage"]["workspace_root"] = str(directory / "workspaces")
    parser["storage"]["state_root"] = str(directory / "state")
    config = directory / "config.cfg"
    with config.open("w", encoding="utf-8") as handle:
        parser.write(handle)
    return config


async def wait_ready(api: httpx.AsyncClient, container: Any, timeout: float = 60) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.to_thread(container.reload)
        if container.status not in {"created", "running", "restarting"}:
            raise RuntimeError("controller container exited before readiness")
        try:
            response = await api.get("/cloud/health/ready", timeout=1)
            if response.status_code == 200:
                return response.json()
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.2)
    raise TimeoutError("controller readiness timeout")


def runtime_assertions(container: Any, runtime_id: str, directory: Path, username: str) -> dict[str, Any]:
    container.reload()
    attrs = container.attrs
    host = attrs.get("HostConfig") or {}
    expected_mounts = {
        "/opt/agent": (directory / "agents" / "agent-code", False),
        "/workspace": (directory / "workspaces" / "agent-code" / username, True),
        "/state/opencode": (directory / "state" / "agent-code" / username / "opencode", True),
    }
    mounts = {item["Destination"]: item for item in attrs.get("Mounts", []) if item.get("Type") == "bind"}
    if set(mounts) != set(expected_mounts):
        raise RuntimeError("runtime bind mount set differs from policy")
    for destination, (source, writable) in expected_mounts.items():
        actual = mounts[destination]
        if Path(actual["Source"]).absolute() != source.absolute() or bool(actual["RW"]) != writable:
            raise RuntimeError("runtime bind mount source or mode differs from policy")
    expected = {"memory": 4096 * 1024**2, "nano_cpus": 4_000_000_000, "pids_limit": 512}
    actual_resources = {
        "memory": int(host.get("Memory") or 0),
        "nano_cpus": int(host.get("NanoCpus") or 0),
        "pids_limit": int(host.get("PidsLimit") or 0),
    }
    if attrs.get("Image") != runtime_id or actual_resources != expected:
        raise RuntimeError("runtime image or resource limits differ from fixture Agent")
    if host.get("Init") is not True or host.get("ReadonlyRootfs") is not True:
        raise RuntimeError("runtime init/read-only-rootfs hardening is absent")
    return {
        "container_id": container.id,
        "image_id": attrs["Image"],
        "resources": actual_resources,
        "init": host["Init"],
        "readonly_rootfs": host["ReadonlyRootfs"],
        "mounts": {
            destination: {"source": str(source), "writable": writable}
            for destination, (source, writable) in expected_mounts.items()
        },
    }


async def verify(version: str) -> dict[str, Any]:
    fixture = uuid.uuid4().hex[:10]
    instance = f"stage34-controller-{fixture}"
    username = f"smoke-{fixture}"
    controller_name = instance
    controller_ref = f"cloud-agent-controller:{version}"
    runtime_ref = f"cloud-agent-runtime:{version}"
    report: dict[str, Any] = {
        "result": "running", "version": version, "instance_id": instance,
        "username": username,
    }
    cleanup_errors: list[str] = []
    client = docker.from_env()
    controller = None
    temporary = tempfile.TemporaryDirectory(prefix=f"{instance}-", dir="/tmp")
    directory = Path(temporary.name).resolve()
    try:
        client.ping()
        controller_image = await asyncio.to_thread(client.images.get, controller_ref)
        runtime_image = await asyncio.to_thread(client.images.get, runtime_ref)
        controller_id = controller_image.id
        runtime_id = runtime_image.id
        port = free_port()
        config = rewrite_fixture(directory, instance, port, runtime_id)
        controller = await asyncio.to_thread(
            client.containers.run,
            controller_ref,
            ["--config", str(config), "--host", "127.0.0.1", "--port", str(port)],
            name=controller_name,
            detach=True,
            network_mode="host",
            volumes={
                "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"},
                str(directory): {"bind": str(directory), "mode": "rw"},
            },
            labels={"cloud.verification": "stage34-controller", "cloud.fixture": fixture},
        )
        await asyncio.to_thread(controller.reload)
        if (
            controller.attrs.get("Image") != controller_id
            or (controller.attrs.get("HostConfig") or {}).get("NetworkMode") != "host"
        ):
            raise RuntimeError("controller image identity or host network differs from fixture")
        base_url = f"http://127.0.0.1:{port}"
        async with httpx.AsyncClient(base_url=base_url, trust_env=False, timeout=30) as api:
            ready = await wait_ready(api, controller)
            document = await api.get("/doc")
            document.raise_for_status()
            assert document.json()["x-cloud-routing"]["websocket"]["pty_supported"] is False
            assert not client.containers.list(all=True, filters={"label": f"cloud.platform_instance={instance}"})

            async def create_session() -> str:
                response = await api.post(
                    "/session", json={"_cloud": {"agent_id": "agent-code", "username": username}}
                )
                response.raise_for_status()
                return response.json()["id"]

            first = await create_session()
            second = await create_session()
            registry = Registry(directory / "platform.db")
            sandbox = registry.get_sandbox("agent-code", username)
            if sandbox is None or not sandbox.container_id:
                raise RuntimeError("controller did not persist a sandbox route")
            runtime = client.containers.get(sandbox.container_id)
            owned = client.containers.list(
                all=True, filters={"label": f"cloud.platform_instance={instance}"}
            )
            if len(owned) != 1 or owned[0].id != runtime.id:
                raise RuntimeError("same-user session fixture did not create exactly one runtime")
            details = runtime_assertions(runtime, runtime_id, directory, username)
            routes = [registry.get_session_route(first), registry.get_session_route(second)]
            if any(route is None or route.sandbox_id != sandbox.sandbox_id for route in routes):
                raise RuntimeError("same-user sessions did not share one sandbox route")
            old = await api.get(f"/session/{first}")
            old.raise_for_status()
            if old.json().get("id") != first:
                raise RuntimeError("old native session lookup returned another session")
            native = await api.get("/global/health", headers={
                "x-cloud-agent-id": "agent-code", "x-cloud-username": username,
            })
            native.raise_for_status()
            health = native.json()
            if health.get("healthy") is not True:
                raise RuntimeError("runtime native health is not healthy")

            await asyncio.to_thread(controller.restart, timeout=20)
            restarted_ready = await wait_ready(api, controller)
            resumed = await api.get(f"/session/{first}")
            resumed.raise_for_status()
            if resumed.json().get("id") != first:
                raise RuntimeError("old session route failed after controller restart")
            after = registry.get_sandbox("agent-code", username)
            if after is None or after.container_id != runtime.id:
                raise RuntimeError("controller restart changed the valid runtime route")
        report.update(
            result="passed",
            images={
                "controller": {"reference": controller_ref, "id": controller_id},
                "runtime": {"reference": runtime_ref, "id": runtime_id},
            },
            controller={"container_id": controller.id, "network_mode": "host", "http_port": port},
            readiness={"initial": ready, "after_restart": restarted_ready},
            sessions={"created": 2, "shared_container": True, "old_route_after_restart": True},
            runtime=details,
            native_health=health,
        )
    except Exception as exc:
        report.update(result="failed", error=type(exc).__name__)
    finally:
        try:
            sandboxes = client.containers.list(
                all=True, filters={"label": f"cloud.platform_instance={instance}"}
            )
            for sandbox in sandboxes:
                if sandbox.labels.get("cloud.platform_instance") != instance:
                    raise RuntimeError("sandbox cleanup ownership mismatch")
                await asyncio.to_thread(sandbox.remove, force=True)
            if client.containers.list(all=True, filters={"label": f"cloud.platform_instance={instance}"}):
                raise RuntimeError("fixture sandbox remains after cleanup")
        except Exception as exc:
            cleanup_errors.append(type(exc).__name__)
        if controller is not None:
            try:
                controller.reload()
                labels = controller.labels
                if labels.get("cloud.verification") != "stage34-controller" or labels.get("cloud.fixture") != fixture:
                    raise RuntimeError("controller cleanup ownership mismatch")
                await asyncio.to_thread(controller.remove, force=True)
            except docker.errors.NotFound:
                pass
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        try:
            temporary.cleanup()
        except Exception as exc:
            cleanup_errors.append(type(exc).__name__)
        client.close()
        if cleanup_errors:
            report.update(result="failed", cleanup_errors=cleanup_errors)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=(ROOT / "VERSION").read_text().strip())
    args = parser.parse_args()
    report = asyncio.run(verify(args.version))
    print(json.dumps(report, indent=2))
    raise SystemExit(report["result"] != "passed")


if __name__ == "__main__":
    main()
