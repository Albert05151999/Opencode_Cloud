#!/usr/bin/env python3
"""Run LiteLLM against deterministic local OpenAI-compatible backends."""

from __future__ import annotations

import asyncio
import argparse
import atexit
import json
import os
import re
import socket
import time
from collections import Counter
from pathlib import Path
from typing import Any, AsyncIterator

import docker
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse


PROJECT = Path(__file__).resolve().parents[1]
CONFIG = PROJECT / "config" / "litellm_config.yaml"
REPORT = PROJECT / "artifacts" / "litellm" / "report.json"
IMAGE = os.environ.get("LITELLM_TEST_IMAGE", "ghcr.io/berriai/litellm:v1.98.0@sha256:20b5044b619055374061a6d5b7b08754cad75aeabbf82ddf4f69cc0cf80ddaf4")
CONTAINER_NAME = "cloud-stage18-litellm-verification"
GATEWAY_URL = "http://127.0.0.1:4001"
LOGICAL_MODELS = ("coding-fast", "coding-quality", "data-fast", "data-quality")


class MockState:
    def __init__(self) -> None:
        self.requests: Counter[str] = Counter()
        self.failures: Counter[str] = Counter()
        self.active: Counter[str] = Counter()
        self.max_active: Counter[str] = Counter()
        self.fail: set[str] = set()
        self.lock = asyncio.Lock()
        self.traces: list[dict[str, Any]] = []

    async def enter(self, backend: str) -> bool:
        async with self.lock:
            self.requests[backend] += 1
            self.active[backend] += 1
            self.max_active[backend] = max(self.max_active[backend], self.active[backend])
            if backend in self.fail:
                self.failures[backend] += 1
                return True
            return False

    async def leave(self, backend: str) -> None:
        async with self.lock:
            self.active[backend] -= 1


def create_mock_app(state: MockState) -> FastAPI:
    app = FastAPI()

    @app.post("/{backend}/v1/chat/completions")
    async def completion(backend: str, request: Request):
        if backend not in {"backend-a", "backend-b"}:
            return JSONResponse(status_code=404, content={"error": {"message": "unknown backend"}})
        body = await request.json()
        state.traces.append({"backend": backend, "model": body.get("model"), "messages": body.get("messages"), "stream": body.get("stream")})
        failed = await state.enter(backend)
        if failed:
            await state.leave(backend)
            return JSONResponse(
                status_code=503,
                content={"error": {"message": f"{backend} unavailable", "type": "server_error"}},
            )
        model = str(body.get("model", "mock-model"))
        if body.get("stream"):
            async def chunks() -> AsyncIterator[bytes]:
                try:
                    await asyncio.sleep(0.20)
                    first = {
                        "id": f"chatcmpl-{backend}", "object": "chat.completion.chunk",
                        "created": int(time.time()), "model": model,
                        "choices": [{"index": 0, "delta": {"role": "assistant", "content": backend}, "finish_reason": None}],
                    }
                    final = {
                        "id": f"chatcmpl-{backend}", "object": "chat.completion.chunk",
                        "created": int(time.time()), "model": model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    }
                    yield f"data: {json.dumps(first)}\n\n".encode()
                    await asyncio.sleep(0.10)
                    yield f"data: {json.dumps(final)}\n\n".encode()
                    yield b"data: [DONE]\n\n"
                finally:
                    await state.leave(backend)

            return StreamingResponse(chunks(), media_type="text/event-stream")
        try:
            await asyncio.sleep(0.20)
            return {
                "id": f"chatcmpl-{backend}", "object": "chat.completion",
                "created": int(time.time()), "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": backend}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        finally:
            await state.leave(backend)

    return app


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("0.0.0.0", 0))
        return int(sock.getsockname()[1])


def free_shared_port(hosts: tuple[str, ...]) -> int:
    """Find one port currently bindable on every requested host address."""
    for _ in range(100):
        with socket.socket() as candidate:
            candidate.bind((hosts[0], 0))
            port = int(candidate.getsockname()[1])
        probes: list[socket.socket] = []
        try:
            for host in hosts:
                probe = socket.socket()
                probe.bind((host, port))
                probes.append(probe)
            return port
        except OSError:
            pass
        finally:
            for probe in probes:
                probe.close()
    raise RuntimeError(f"unable to find a port bindable on {hosts}")


def cleanup(client: docker.DockerClient) -> None:
    try:
        container = client.containers.get(CONTAINER_NAME)
    except docker.errors.NotFound:
        return
    if container.labels.get("cloud.verification") != "stage18":
        raise RuntimeError("refusing to remove a container without the stage18 ownership label")
    container.remove(force=True)


async def wait_http(client: httpx.AsyncClient, url: str, timeout: float = 45) -> httpx.Response:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = await client.get(url)
            if response.status_code < 500:
                return response
        except httpx.HTTPError as exc:
            last_error = exc
        await asyncio.sleep(0.25)
    raise RuntimeError(f"timed out waiting for {url}: {last_error}")


async def stream_call(client: httpx.AsyncClient, model: str) -> tuple[str, float, str | None]:
    started = time.perf_counter()
    content = ""
    first_ms: float | None = None
    async with client.stream(
        "POST", f"{GATEWAY_URL}/v1/chat/completions",
        json={"model": model, "messages": [{"role": "user", "content": "ping"}], "stream": True},
    ) as response:
        response.raise_for_status()
        model_id = response.headers.get("x-litellm-model-id")
        async for line in response.aiter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            payload = json.loads(line[6:])
            delta = payload["choices"][0].get("delta", {}).get("content", "")
            if delta and first_ms is None:
                first_ms = (time.perf_counter() - started) * 1000
            content += delta
    assert first_ms is not None
    assert (time.perf_counter() - started) * 1000 - first_ms >= 50, "stream was buffered"
    return content, first_ms, model_id


async def verify(integration_hook=None, gateway_port: int | None = None) -> dict[str, Any]:
    global GATEWAY_URL
    if gateway_port is not None and not 1 <= gateway_port <= 65535:
        raise ValueError("gateway_port must be between 1 and 65535")
    state = MockState()
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_mock_app(state), host="0.0.0.0", port=port, log_level="warning"))
    server_task = asyncio.create_task(server.serve())
    while not server.started:
        if server_task.done():
            await server_task
        await asyncio.sleep(0.05)

    docker_client = docker.from_env()
    docker_client.ping()
    bridge_ip = docker_client.networks.get("bridge").attrs["IPAM"]["Config"][0]["Gateway"]
    if gateway_port is None:
        gateway_port = free_shared_port(("127.0.0.1", bridge_ip))
    GATEWAY_URL = f"http://127.0.0.1:{gateway_port}"
    cleanup(docker_client)
    atexit.register(cleanup, docker_client)
    backend_a = f"http://host.docker.internal:{port}/backend-a/v1"
    backend_b = f"http://host.docker.internal:{port}/backend-b/v1"
    environment = {name + "_API_KEY": "stage18-local-only" for name in ("CODING_FAST", "CODING_QUALITY", "DATA_FAST", "DATA_QUALITY")}
    for prefix in ("CODING_FAST", "CODING_QUALITY", "DATA_FAST", "DATA_QUALITY"):
        environment[f"{prefix}_MODEL"] = "openai/mock-model"
        environment[f"{prefix}_1_API_BASE"] = backend_a
        environment[f"{prefix}_2_API_BASE"] = backend_b

    try:
        container = await asyncio.to_thread(
            docker_client.containers.run,
            IMAGE,
            ["--config", "/app/config.yaml", "--port", "4000"],
            name=CONTAINER_NAME,
            detach=True,
            ports={"4000/tcp": [("127.0.0.1", gateway_port), (bridge_ip, gateway_port)]},
            extra_hosts={"host.docker.internal": "host-gateway"},
            volumes={str(CONFIG): {"bind": "/app/config.yaml", "mode": "ro"},
                     str(PROJECT / "deploy/cloud_logging.py"): {"bind": "/app/cloud_logging.py", "mode": "ro"}},
            environment=environment,
            labels={"cloud.verification": "stage18"},
            security_opt=["no-new-privileges:true"],
            cap_drop=["ALL"],
        )
        async with httpx.AsyncClient(trust_env=False, timeout=20, follow_redirects=True) as http:
            health = await wait_http(http, f"{GATEWAY_URL}/health/liveliness")
            health.raise_for_status()
            probe = await asyncio.to_thread(
                docker_client.containers.run,
                IMAGE,
                ["-c", f"import urllib.request; urllib.request.urlopen('http://host.docker.internal:{gateway_port}/health/liveliness', timeout=3)"],
                entrypoint="python",
                extra_hosts={"host.docker.internal": "host-gateway"},
                remove=True,
            )
            if integration_hook is not None:
                await integration_hook(state)

            direct_results: dict[str, str] = {}
            for logical_model in LOGICAL_MODELS:
                response = await http.post(
                    f"{GATEWAY_URL}/v1/chat/completions",
                    json={"model": logical_model, "messages": [{"role": "user", "content": "ping"}]},
                )
                response.raise_for_status()
                direct_results[logical_model] = response.json()["choices"][0]["message"]["content"]

            before_balance = state.requests.copy()
            streams = await asyncio.gather(*(stream_call(http, "coding-fast") for _ in range(8)))
            balanced = {
                backend: state.requests[backend] - before_balance[backend]
                for backend in ("backend-a", "backend-b")
            }
            assert all(value > 0 for value in balanced.values()), balanced
            assert abs(balanced["backend-a"] - balanced["backend-b"]) <= 2, balanced
            assert {item[0] for item in streams} == {"backend-a", "backend-b"}

            state.fail.add("backend-a")
            failures_before = state.failures["backend-a"]
            successes_before = state.requests["backend-b"]
            failover_responses = []
            for _ in range(8):
                response = await http.post(
                    f"{GATEWAY_URL}/v1/chat/completions",
                    json={"model": "coding-quality", "messages": [{"role": "user", "content": "failover"}]},
                )
                response.raise_for_status()
                failover_responses.append(response.json()["choices"][0]["message"]["content"])
            assert state.failures["backend-a"] > failures_before
            assert state.requests["backend-b"] > successes_before
            assert set(failover_responses) == {"backend-b"}
            failures_at_cooldown = state.failures["backend-a"]
            for _ in range(4):
                response = await http.post(
                    f"{GATEWAY_URL}/v1/chat/completions",
                    json={"model": "coding-quality", "messages": [{"role": "user", "content": "cooldown"}]},
                )
                response.raise_for_status()
                assert response.json()["choices"][0]["message"]["content"] == "backend-b"
            assert state.failures["backend-a"] == failures_at_cooldown, "failed deployment was not cooled down"

            metrics_response = await wait_http(http, f"{GATEWAY_URL}/metrics")
            metrics_response.raise_for_status()
            metrics = metrics_response.text
            REPORT.parent.mkdir(parents=True, exist_ok=True)
            (REPORT.parent / "metrics.prom").write_text(metrics, encoding="utf-8")
            required_metrics = (
                "litellm_request_total_latency_metric_count",
                "litellm_llm_api_latency_metric_count",
                "litellm_llm_api_time_to_first_token_metric_count",
                "litellm_proxy_total_requests_metric",
            )
            for metric in required_metrics:
                assert metric in metrics, metric
            ttft_samples = [
                float(value) for value in re.findall(
                    r"^litellm_llm_api_time_to_first_token_metric_count\{[^}]*\} ([0-9.eE+-]+)$",
                    metrics, flags=re.MULTILINE,
                )
            ]
            assert sum(ttft_samples) >= 8, ttft_samples

        await asyncio.to_thread(container.reload)
        image_id = container.image.id
        repo_digests = container.image.attrs.get("RepoDigests", [])
        logs = container.logs(tail=200).decode(errors="replace")
        report = {
            "result": "passed",
            "image_reference": IMAGE,
            "image_id": image_id,
            "repo_digests": repo_digests,
            "gateway_port": gateway_port,
            "gateway_bind": f"127.0.0.1:{gateway_port}",
            "sandbox_gateway_bind": f"{bridge_ip}:{gateway_port}",
            "sandbox_gateway_health": "passed",
            "health": health.json(),
            "logical_model_results": direct_results,
            "least_busy_concurrent_distribution": balanced,
            "stream_ttft_ms": [round(item[1], 2) for item in streams],
            "stream_model_ids": [item[2] for item in streams],
            "failover": {
                "failed_backend": "backend-a",
                "backend_a_failures": state.failures["backend-a"],
                "successful_responses": len(failover_responses),
                "response_backends": sorted(set(failover_responses)),
                "cooldown_probe_requests": 4,
                "additional_failed_backend_calls_during_cooldown": state.failures["backend-a"] - failures_at_cooldown,
            },
            "mock_request_counts": dict(state.requests),
            "ttft_metric_count": sum(ttft_samples),
            "required_metrics": list(required_metrics),
            "startup_log_tail": logs[-4000:],
            "checks": [
                "all four logical models completed through LiteLLM",
                "eight concurrent streams reached both equivalent deployments under least-busy",
                "streaming responses emitted content before completion",
                "one unavailable deployment retried or cooled down and every request succeeded on its peer",
                "Prometheus exposed request latency, provider latency, request totals, and streaming TTFT",
                "no external model or provider credential was used",
            ],
        }
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report
    except Exception as exc:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({"result": "failed", "error": str(exc)}, indent=2) + "\n", encoding="utf-8")
        try:
            failed_container = docker_client.containers.get(CONTAINER_NAME)
            (REPORT.parent / "failure.log").write_bytes(failed_container.logs(tail=300))
        except docker.errors.NotFound:
            pass
        raise
    finally:
        cleanup(docker_client)
        atexit.unregister(cleanup)
        server.should_exit = True
        await server_task


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway-port", type=int, default=None)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(gateway_port=args.gateway_port)), indent=2))
