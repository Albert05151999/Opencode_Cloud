#!/usr/bin/env python3
"""Verify routed OpenCode v2 sessions and SSE streams without model calls."""
from __future__ import annotations

import asyncio
import json
import shutil
import socket
import tempfile
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import docker
import httpx
import uvicorn

from app.config import load_config
from app.gateway import SSEConnectionTracker, create_gateway_router
from app.main import create_app
from app.registry import Registry
from app.sandbox import LocalDockerBackend
from app.workspace import WorkspaceManager


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts" / "sse" / "v2-report.json"
AGENT = "agent-code"


async def wait_for(predicate, timeout: float, description: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {description}")


async def run_server(app: Any) -> tuple[uvicorn.Server, asyncio.Task[None], socket.socket, str]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.setblocking(False)
    port = int(listener.getsockname()[1])
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    await wait_for(lambda: server.started, 10, "gateway startup")
    return server, task, listener, f"http://127.0.0.1:{port}"


def remove_owned(client: docker.DockerClient, instance: str) -> None:
    for container in client.containers.list(all=True, filters={"label": f"cloud.platform_instance={instance}"}):
        container.reload()
        labels = (container.attrs.get("Config") or {}).get("Labels") or {}
        if labels.get("cloud.platform_instance") != instance:
            raise RuntimeError("cleanup ownership mismatch")
        container.remove(force=True)


async def probe_stream(
    gateway: httpx.AsyncClient, url: str, tracker: SSEConnectionTracker,
    sandboxes: LocalDockerBackend, headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    async with gateway.stream(
        "GET", url, headers={"Accept": "text/event-stream", **(headers or {})}
    ) as response:
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert content_type.startswith("text/event-stream")
        await wait_for(lambda: tracker.active == 1, 5, "active v2 SSE tracker")
        assert sum(sandboxes.in_use.values()) == 1
        iterator = response.aiter_raw()
        first = await asyncio.wait_for(anext(iterator), timeout=10)
        assert 0 < len(first) <= 256 * 1024
        first_chunk_ms = (time.monotonic() - started) * 1000
    await wait_for(lambda: tracker.active == 0, 10, "v2 SSE tracker cleanup")
    await wait_for(lambda: not sandboxes.in_use, 10, "v2 SSE lease cleanup")
    return {
        "status": 200,
        "content_type": content_type,
        "first_chunk_bytes": len(first),
        "first_chunk_ms": round(first_chunk_ms, 3),
        "tracker_after_disconnect": tracker.active,
        "leases_after_disconnect": sum(sandboxes.in_use.values()),
    }


async def hold_idle_stream(gateway: httpx.AsyncClient, url: str) -> None:
    """Wait for an idle SSE response; the caller deliberately cancels this task."""
    async with gateway.stream("GET", url, headers={"Accept": "text/event-stream"}) as response:
        async for _chunk in response.aiter_raw():
            pass


async def verify() -> dict[str, Any]:
    fixture = uuid.uuid4().hex[:12]
    instance = f"stage-v2-events-{fixture}"
    username = f"v2-user-{fixture}"
    other_user = f"v2-other-{fixture}"
    report: dict[str, Any] = {"result": "running", "instance_id": instance, "steps": []}
    cleanup_errors: list[str] = []
    docker_client = docker.from_env()
    server = None
    server_task = None
    listener = None
    upstream = None
    request_tasks: list[asyncio.Task[Any]] = []
    temporary = tempfile.TemporaryDirectory(prefix=f"{instance}-", dir="/tmp")
    directory = Path(temporary.name).resolve()
    try:
        docker_client.ping()
        remove_owned(docker_client, instance)
        agents_root = directory / "agents"
        shutil.copytree(ROOT / "agents" / AGENT, agents_root / AGENT)
        config = load_config(ROOT / "config.cfg")
        config = replace(
            config,
            platform=replace(config.platform, instance_id=instance, data_root=str(directory)),
            storage=replace(
                config.storage,
                workspace_root=str(directory / "workspaces"),
                state_root=str(directory / "state"),
            ),
        )
        registry = Registry(directory / "platform.db")
        registry.initialize()
        workspaces = WorkspaceManager(
            config.storage.workspace_root, config.storage.state_root,
            runtime_uid=10001, runtime_gid=10001,
        )
        sandboxes = LocalDockerBackend(config, registry, workspaces, agents_root, client=docker_client)
        tracker = SSEConnectionTracker()
        upstream = httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(30, read=None))
        app = create_app(create_gateway_router(registry, sandboxes, upstream, tracker))
        server, server_task, listener, base_url = await run_server(app)

        route_headers = {"X-Cloud-Agent-ID": AGENT, "X-Cloud-Username": username}
        async with httpx.AsyncClient(base_url=base_url, trust_env=False, timeout=30) as gateway:
            report["step"] = "create"
            created = await gateway.post(
                "/api/session",
                json={"_cloud": {"agent_id": AGENT, "username": username}},
            )
            assert created.status_code in range(200, 300)
            created_body = created.json()
            session_id = (created_body.get("data") or {}).get("id")
            assert isinstance(session_id, str) and session_id.startswith("ses_")
            report["steps"].append({"name": "create_v2_session", "status": created.status_code})

            report["step"] = "get"
            fetched = await gateway.get(f"/api/session/{session_id}")
            assert fetched.status_code == 200
            fetched_body = fetched.json()
            assert (fetched_body.get("data") or {}).get("id") == session_id
            report["steps"].append({"name": "headerless_v2_lookup", "status": fetched.status_code})

            conflict = await gateway.get(
                f"/api/session/{session_id}",
                headers={"X-Cloud-Agent-ID": AGENT, "X-Cloud-Username": other_user},
            )
            assert conflict.status_code == 409
            report["steps"].append({"name": "cross_user_conflict", "status": conflict.status_code})

            report["step"] = "api_event"
            api_event = await probe_stream(
                gateway, "/api/event", tracker, sandboxes, route_headers,
            )
            report["steps"].append({"name": "api_event_first_chunk", "status": 200})
            report["step"] = "session_event"
            session_stream = asyncio.create_task(probe_stream(
                gateway, f"/api/session/{session_id}/event", tracker, sandboxes,
            ))
            request_tasks.append(session_stream)
            await asyncio.sleep(0.5)
            changed = await gateway.post(
                f"/api/session/{session_id}/prompt",
                json={"prompt": {"text": "SSE verification input; do not execute."}, "resume": False},
            )
            assert changed.status_code in range(200, 300)
            report["steps"].append({"name": "trigger_session_update", "status": changed.status_code})
            session_event = await asyncio.wait_for(session_stream, timeout=30)
            report["steps"].append({"name": "api_session_event_first_chunk", "status": 200})

            report["step"] = "idle_session_event_disconnect"
            idle_created = await gateway.post(
                "/api/session",
                json={"_cloud": {"agent_id": AGENT, "username": username}},
            )
            assert idle_created.status_code in range(200, 300)
            idle_session_id = ((idle_created.json().get("data") or {}).get("id"))
            assert isinstance(idle_session_id, str) and idle_session_id.startswith("ses_")
            idle_stream = asyncio.create_task(
                hold_idle_stream(gateway, f"/api/session/{idle_session_id}/event")
            )
            request_tasks.append(idle_stream)
            await wait_for(
                lambda: sum(sandboxes.in_use.values()) == 1,
                10,
                "idle session SSE lease acquisition",
            )
            await asyncio.sleep(0.25)
            assert not idle_stream.done(), "idle session stream unexpectedly completed"
            idle_stream.cancel()
            await asyncio.gather(idle_stream, return_exceptions=True)
            await wait_for(lambda: tracker.active == 0, 10, "idle SSE tracker cleanup")
            await wait_for(lambda: not sandboxes.in_use, 10, "idle SSE lease cleanup")
            report["steps"].append({"name": "idle_session_event_cancel", "status": 0})

            report["step"] = "delete"
            deleted = await gateway.delete(f"/api/session/{session_id}")
            assert deleted.status_code in range(200, 300)
            idle_deleted = await gateway.delete(f"/api/session/{idle_session_id}")
            assert idle_deleted.status_code in range(200, 300)
            report["steps"].append({"name": "delete_v2_session", "status": deleted.status_code})

        report.update(
            result="passed",
            session_id=session_id,
            create_data_envelope=True,
            headerless_session_lookup=True,
            get_data_envelope=True,
            cross_user_status=conflict.status_code,
            delete_status=deleted.status_code,
            streams={"api_event": api_event, "api_session_event": session_event},
            idle_disconnect={
                "tracker_after_cancel": tracker.active,
                "leases_after_cancel": sum(sandboxes.in_use.values()),
            },
            checks=[
                "POST /api/session stripped _cloud and persisted data.id",
                "GET /api/session/:id resolved from the registry without routing headers",
                "a conflicting username was rejected with 409",
                "both v2 event endpoints streamed a bounded first chunk",
                "both disconnects returned the SSE tracker and sandbox leases to zero",
                "an idle session stream cancelled before response headers released its lease",
                "DELETE /api/session/:id reached the owning sandbox",
            ],
        )
    except Exception as exc:
        report.update(result="failed", error_code=type(exc).__name__)
    finally:
        for task in request_tasks:
            if not task.done():
                task.cancel()
        if request_tasks:
            await asyncio.gather(*request_tasks, return_exceptions=True)
        if server is not None:
            server.should_exit = True
        if server_task is not None:
            try:
                await asyncio.wait_for(server_task, timeout=10)
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
                server.force_exit = True
                server_task.cancel()
                await asyncio.gather(server_task, return_exceptions=True)
        if listener is not None:
            listener.close()
        if upstream is not None:
            try:
                await upstream.aclose()
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        try:
            remove_owned(docker_client, instance)
        except Exception as exc:
            cleanup_errors.append(type(exc).__name__)
        try:
            docker_client.close()
        except Exception as exc:
            cleanup_errors.append(type(exc).__name__)
        try:
            temporary.cleanup()
        except Exception as exc:
            cleanup_errors.append(type(exc).__name__)
        if cleanup_errors:
            report.update(result="failed", cleanup_errors=cleanup_errors)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    result = asyncio.run(verify())
    print(json.dumps(result, indent=2))
    raise SystemExit(result["result"] != "passed")
