#!/usr/bin/env python3
"""Exercise routed OpenCode SSE streams with two real Agent x User sandboxes."""

from __future__ import annotations

import asyncio
import atexit
import json
import shutil
import socket
import time
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


PROJECT = Path(__file__).resolve().parents[1]
TEST_ROOT = Path("/tmp/cloud-agent-stage15-verification")
REPORT = PROJECT / "artifacts" / "sse" / "report.json"
INSTANCE = "stage15-verification"
CAPTURE_LIMIT = 256 * 1024


def remove_instance_containers(client: docker.DockerClient) -> None:
    """Remove only containers carrying this verification instance label."""

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


def prepare_agent() -> Path:
    agents_root = TEST_ROOT / "agents"
    shutil.copytree(PROJECT / "agents" / "agent-code", agents_root / "agent-code")
    return agents_root


async def wait_for(predicate: Any, timeout: float, description: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {description}")


async def collect_sse(
    client: httpx.AsyncClient,
    base_url: str,
    username: str,
    name: str,
    ready: asyncio.Event,
    captures: dict[str, dict[str, Any]],
) -> None:
    started = time.monotonic()
    headers = {
        "Accept": "text/event-stream",
        "X-Cloud-Agent-ID": "agent-code",
        "X-Cloud-Username": username,
    }
    async with client.stream("GET", f"{base_url}/event", headers=headers) as response:
        assert response.status_code == 200, (name, response.status_code, await response.aread())
        assert response.headers.get("content-type", "").startswith("text/event-stream")
        ready.set()
        captured = bytearray()
        first_chunk_ms: float | None = None
        chunks = 0
        async for chunk in response.aiter_raw():
            if first_chunk_ms is None:
                first_chunk_ms = (time.monotonic() - started) * 1000
            chunks += 1
            remaining = CAPTURE_LIMIT - len(captured)
            if remaining > 0:
                captured.extend(chunk[:remaining])
            captures[name] = {
                "username": username,
                "body": bytes(captured),
                "captured_bytes": len(captured),
                "chunks": chunks,
                "first_chunk_ms": first_chunk_ms,
            }


async def verify_global_event(client: httpx.AsyncClient, base_url: str) -> str:
    headers = {
        "Accept": "text/event-stream",
        "X-Cloud-Agent-ID": "agent-code",
        "X-Cloud-Username": "alice",
    }
    async with client.stream("GET", f"{base_url}/global/event", headers=headers) as response:
        assert response.status_code == 200, response.status_code
        content_type = response.headers.get("content-type", "")
        assert content_type.startswith("text/event-stream"), content_type
        return content_type


async def run_server(app: Any) -> tuple[uvicorn.Server, asyncio.Task[None], socket.socket, str]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.setblocking(False)
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    task = asyncio.create_task(server.serve(sockets=[listener]))
    await wait_for(lambda: server.started, 10, "temporary gateway startup")
    return server, task, listener, f"http://127.0.0.1:{port}"


async def verify() -> dict[str, Any]:
    client = docker.from_env()
    client.ping()
    remove_instance_containers(client)
    remove_test_root()
    TEST_ROOT.mkdir(parents=True)
    agents_root = prepare_agent()

    def cleanup() -> None:
        remove_instance_containers(client)
        remove_test_root()

    atexit.register(cleanup)
    config = load_config(PROJECT / "config.cfg")
    config = replace(config, platform=replace(config.platform, instance_id=INSTANCE))
    registry = Registry(TEST_ROOT / "platform.db")
    registry.initialize()
    workspaces = WorkspaceManager(
        TEST_ROOT / "workspaces",
        TEST_ROOT / "state",
        runtime_uid=10001,
        runtime_gid=10001,
    )
    sandboxes = LocalDockerBackend(config, registry, workspaces, agents_root, client=client)
    initial_endpoints = await asyncio.gather(
        sandboxes.acquire("agent-code", "alice"),
        sandboxes.acquire("agent-code", "bob"),
    )
    for endpoint in initial_endpoints:
        await sandboxes.release(endpoint)

    tracker = SSEConnectionTracker()
    upstream = httpx.AsyncClient(trust_env=False, timeout=None)
    app = create_app(create_gateway_router(registry, sandboxes, upstream, tracker))
    server = None
    server_task = None
    listener = None
    stream_tasks: list[asyncio.Task[None]] = []
    try:
        server, server_task, listener, base_url = await run_server(app)
        async with httpx.AsyncClient(trust_env=False, timeout=None) as gateway:
            global_content_type = await verify_global_event(gateway, base_url)
            await wait_for(lambda: tracker.active == 0, 5, "global SSE tracker cleanup")

            captures: dict[str, dict[str, Any]] = {}
            ready = {name: asyncio.Event() for name in ("alice-1", "alice-2", "bob-1", "bob-2")}
            for name, username in (
                ("alice-1", "alice"),
                ("alice-2", "alice"),
                ("bob-1", "bob"),
                ("bob-2", "bob"),
            ):
                stream_tasks.append(
                    asyncio.create_task(
                        collect_sse(gateway, base_url, username, name, ready[name], captures)
                    )
                )
            await asyncio.wait_for(
                asyncio.gather(*(event.wait() for event in ready.values())), timeout=10
            )
            await wait_for(lambda: tracker.active == 4, 5, "four active routed SSE streams")
            assert sum(sandboxes.in_use.values()) == 4

            async def create_session(username: str) -> str:
                response = await gateway.post(
                    f"{base_url}/session",
                    json={"_cloud": {"agent_id": "agent-code", "username": username}},
                )
                response.raise_for_status()
                session_id = response.json().get("id")
                assert isinstance(session_id, str) and session_id.startswith("ses_")
                return session_id

            alice_session, bob_session = await asyncio.gather(
                create_session("alice"), create_session("bob")
            )

            def routed_events_arrived() -> bool:
                return all(
                    item in captures and expected.encode() in captures[item]["body"]
                    for item, expected in (
                        ("alice-1", alice_session),
                        ("alice-2", alice_session),
                        ("bob-1", bob_session),
                        ("bob-2", bob_session),
                    )
                )

            await wait_for(routed_events_arrived, 15, "user-specific session events")
            for name in ("alice-1", "alice-2"):
                assert bob_session.encode() not in captures[name]["body"], name
            for name in ("bob-1", "bob-2"):
                assert alice_session.encode() not in captures[name]["body"], name
            assert all(item["captured_bytes"] <= CAPTURE_LIMIT for item in captures.values())

            for task in stream_tasks:
                task.cancel()
            await asyncio.gather(*stream_tasks, return_exceptions=True)
            await wait_for(lambda: tracker.active == 0, 10, "SSE tracker returning to zero")
            await wait_for(lambda: not sandboxes.in_use, 10, "all SSE leases released")

            report = {
                "result": "passed",
                "instance_id": INSTANCE,
                "alice_session_id": alice_session,
                "bob_session_id": bob_session,
                "event_clients": 4,
                "global_event_content_type": global_content_type,
                "tracker_after_disconnect": tracker.active,
                "leases_after_disconnect": sum(sandboxes.in_use.values()),
                "capture_limit_bytes_per_client": CAPTURE_LIMIT,
                "bounded_read_evidence": {
                    name: {
                        "captured_bytes": item["captured_bytes"],
                        "chunks": item["chunks"],
                        "first_chunk_ms": round(item["first_chunk_ms"], 3),
                    }
                    for name, item in sorted(captures.items())
                },
                "checks": [
                    "two Alice and two Bob /event clients connected through the gateway",
                    "each client observed only its routed user's new session ID",
                    "/global/event returned text/event-stream",
                    "client cancellation released upstream streams and tracker returned to zero",
                    "each client capture was bounded to 256 KiB",
                ],
            }
    finally:
        for task in stream_tasks:
            if not task.done():
                task.cancel()
        if stream_tasks:
            await asyncio.gather(*stream_tasks, return_exceptions=True)
        await upstream.aclose()
        if server is not None:
            server.should_exit = True
        if server_task is not None:
            await asyncio.wait_for(server_task, timeout=10)
        if listener is not None:
            listener.close()

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    cleanup()
    atexit.unregister(cleanup)
    return report


if __name__ == "__main__":
    print(json.dumps(asyncio.run(verify()), indent=2))
