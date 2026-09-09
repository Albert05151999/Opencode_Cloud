#!/usr/bin/env python3
"""Measure paired LiteLLM-to-physical-provider streaming TTFT overhead.

The production gateway is inspected but never changed. A temporary LiteLLM
container uses the same image, configuration and provider credentials while a
local relay records the physical-provider TTFT for each sequential request.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import math
import socket
import time
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import docker
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "litellm_config.yaml"
OUTPUT_ROOT = ROOT / "artifacts" / "perf" / "gateway-ttft"
LOGICAL_MODELS = ("coding-fast", "coding-quality", "data-fast", "data-quality")
PREFIXES = {
    "coding-fast": "CODING_FAST",
    "coding-quality": "CODING_QUALITY",
    "data-fast": "DATA_FAST",
    "data-quality": "DATA_QUALITY",
}
REQUIRED_SUFFIXES = ("MODEL", "API_KEY", "1_API_BASE", "2_API_BASE")
OWNERSHIP_LABEL = "cloud.verification.gateway-ttft"
NEGATIVE_TOLERANCE_MS = 5.0
MAX_SSE_FRAME_BYTES = 1024 * 1024


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def safe_error(exc: BaseException) -> str:
    """Return a non-secret failure classification only."""
    return type(exc).__name__


def parse_sse_content(frame: bytes) -> bool:
    data_lines = []
    for line in frame.splitlines():
        if line.startswith(b"data:"):
            data_lines.append(line[5:].lstrip())
    if not data_lines:
        return False
    payload = b"\n".join(data_lines)
    if payload == b"[DONE]":
        return False
    try:
        event = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    return any(choice.get("delta", {}).get("content") for choice in event.get("choices", []))


class RelayState:
    def __init__(self, targets: dict[tuple[str, int], str]) -> None:
        self.targets = targets
        self.traces: list[dict[str, Any]] = []
        self.client = httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(600.0))

    async def close(self) -> None:
        await self.client.aclose()

    async def forward(self, logical: str, slot: int, request: Request):
        target_base = self.targets[(logical, slot)].rstrip("/")
        target = target_base + "/chat/completions"
        body = await request.body()
        excluded = {"host", "content-length", "connection", "transfer-encoding"}
        headers = {key: value for key, value in request.headers.items() if key.lower() not in excluded}
        trace: dict[str, Any] = {
            "logical_model": logical,
            "slot": slot,
            "status": "running",
            "physical_ttft_ms": None,
            "error": None,
        }
        self.traces.append(trace)
        upstream: httpx.Response | None = None
        try:
            outbound = self.client.build_request("POST", target, headers=headers, content=body)
            started = time.perf_counter()
            upstream = await self.client.send(outbound, stream=True)
            upstream.raise_for_status()
        except Exception as exc:
            trace.update(status="failed", error=safe_error(exc))
            if upstream is not None:
                with suppress(Exception):
                    await upstream.aclose()
            return JSONResponse(
                status_code=502,
                content={"error": {"type": "RelayUpstreamError", "message": "upstream relay failed"}},
            )

        assert upstream is not None

        async def chunks() -> AsyncIterator[bytes]:
            buffer = b""
            first_seen = False
            try:
                # aiter_bytes transparently decodes provider content encoding; the
                # corresponding response header is removed below.
                async for chunk in upstream.aiter_bytes():
                    arrived_at = time.perf_counter()
                    if not first_seen:
                        buffer += chunk
                        while True:
                            lf_at = buffer.find(b"\n\n")
                            crlf_at = buffer.find(b"\r\n\r\n")
                            candidates = [(at, width) for at, width in ((lf_at, 2), (crlf_at, 4)) if at >= 0]
                            if not candidates:
                                if len(buffer) > MAX_SSE_FRAME_BYTES:
                                    raise ValueError("SSEFrameTooLarge")
                                break
                            at, width = min(candidates)
                            if at > MAX_SSE_FRAME_BYTES:
                                raise ValueError("SSEFrameTooLarge")
                            frame, buffer = buffer[:at], buffer[at + width :]
                            if parse_sse_content(frame):
                                trace["physical_ttft_ms"] = (arrived_at - started) * 1000
                                first_seen = True
                                break
                    yield chunk
                if first_seen:
                    trace["status"] = "passed"
                else:
                    trace.update(status="failed", error="NoContentToken")
            except Exception as exc:
                trace.update(status="failed", error=safe_error(exc))
                return
            finally:
                await upstream.aclose()

        response_headers = {
            key: value
            for key, value in upstream.headers.items()
            if key.lower() not in {"content-length", "connection", "transfer-encoding", "content-encoding"}
        }
        return StreamingResponse(chunks(), status_code=upstream.status_code, headers=response_headers)


def create_relay(state: RelayState) -> FastAPI:
    app = FastAPI()

    @app.post("/{logical}/{slot}/v1/chat/completions")
    async def relay(logical: str, slot: int, request: Request):
        if logical not in PREFIXES or slot not in (1, 2):
            raise ValueError("unknown relay route")
        return await state.forward(logical, slot, request)

    return app


def production_gateway(client: docker.DockerClient, port: int):
    matches = []
    for container in client.containers.list():
        for bindings in container.attrs.get("NetworkSettings", {}).get("Ports", {}).values():
            if any(binding.get("HostIp") == "127.0.0.1" and binding.get("HostPort") == str(port) for binding in bindings or []):
                matches.append(container)
                break
    if len(matches) != 1:
        raise RuntimeError("ProductionGatewayCardinality")
    return matches[0]


def provider_environment(container) -> dict[str, str]:
    source: dict[str, str] = {}
    for item in container.attrs.get("Config", {}).get("Env", []):
        key, separator, value = item.partition("=")
        if separator:
            source[key] = value
    required = [f"{prefix}_{suffix}" for prefix in PREFIXES.values() for suffix in REQUIRED_SUFFIXES]
    if any(not source.get(key) for key in required):
        raise RuntimeError("MissingProviderEnvironment")
    return {key: source[key] for key in required}


async def wait_ready(base_url: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient(trust_env=False, timeout=3.0, follow_redirects=True) as client:
        while time.monotonic() < deadline:
            try:
                response = await client.get(base_url + "/health/liveliness")
                if response.is_success:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.25)
    raise TimeoutError("TemporaryGatewayReadiness")


async def one_request(client: httpx.AsyncClient, relay: RelayState, logical: str) -> dict[str, Any]:
    request_id = "load_" + uuid.uuid4().hex
    before = len(relay.traces)
    started = time.perf_counter()
    first_at: float | None = None
    record: dict[str, Any] = {
        "request_id": request_id,
        "logical_model": logical,
        "slot": None,
        "model_id": None,
        "gateway_ttft_ms": None,
        "physical_ttft_ms": None,
        "paired_overhead_ms": None,
        "litellm_overhead_header_ms": None,
        "litellm_overhead_header_available": False,
        "attempted_retries": None,
        "attempted_fallbacks": None,
        "status": "failed",
        "error": None,
        "relay_attempts": "[]",
    }
    try:
        async with asyncio.timeout(600):
            async with client.stream(
                "POST",
                "/v1/chat/completions",
                json={
                    "model": logical,
                    "messages": [{"role": "user", "content": "Reply briefly: " + request_id}],
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                record["model_id"] = response.headers.get("x-litellm-model-id")
                record["attempted_retries"] = int(response.headers.get("x-litellm-attempted-retries", "0"))
                record["attempted_fallbacks"] = int(response.headers.get("x-litellm-attempted-fallbacks", "0"))
                overhead_header = response.headers.get("x-litellm-overhead-duration-ms")
                if overhead_header is not None:
                    parsed_header = float(overhead_header)
                    if not math.isfinite(parsed_header):
                        raise ValueError("NonFiniteLiteLLMOverheadHeader")
                    record["litellm_overhead_header_ms"] = parsed_header
                    record["litellm_overhead_header_available"] = True
                lines: list[str] = []
                async for line in response.aiter_lines():
                    if not line:
                        if lines:
                            payload = "\n".join(lines)
                            lines = []
                            if payload != "[DONE]":
                                event = json.loads(payload)
                                if first_at is None and any(
                                    choice.get("delta", {}).get("content")
                                    for choice in event.get("choices", [])
                                ):
                                    first_at = time.perf_counter()
                        continue
                    if line.startswith("data:"):
                        lines.append(line[5:].lstrip())
        attempts = relay.traces[before:]
        if len(attempts) != 1:
            raise RuntimeError("RelayAttemptCardinality")
        trace = attempts[0]
        if trace["status"] != "passed" or trace["physical_ttft_ms"] is None:
            raise RuntimeError("RelayTraceIncomplete")
        if first_at is None:
            raise RuntimeError("NoGatewayContentToken")
        record["slot"] = trace["slot"]
        record["gateway_ttft_ms"] = (first_at - started) * 1000
        record["physical_ttft_ms"] = trace["physical_ttft_ms"]
        record["paired_overhead_ms"] = record["gateway_ttft_ms"] - record["physical_ttft_ms"]
        if record["attempted_retries"] or record["attempted_fallbacks"]:
            raise RuntimeError("UnexpectedRetryOrFallback")
        if record["model_id"] != f"{logical}-{record['slot']}":
            raise RuntimeError("ModelSlotMismatch")
        if record["paired_overhead_ms"] < -NEGATIVE_TOLERANCE_MS:
            raise RuntimeError("NegativeOverheadBeyondTolerance")
        record["status"] = "passed"
    except Exception as exc:
        record["error"] = safe_error(exc)
        record['relay_attempts'] = json.dumps(relay.traces[before:])
    return record


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = list(records[0]) if records else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


async def verify(rounds: int, production_port: int, selected_models=LOGICAL_MODELS) -> dict[str, Any]:
    if rounds != 20:
        raise ValueError("This acceptance check requires exactly 20 samples per model")
    run_dir = OUTPUT_ROOT / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
    run_dir.mkdir(parents=True, exist_ok=False)
    report_path = run_dir / "report.json"
    report: dict[str, Any] = {
        "result": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "samples_per_model": rounds,
        "negative_tolerance_ms": NEGATIVE_TOLERANCE_MS,
        "scope": (
            "A temporary LiteLLM uses the production container image and repository config, with a relay inserted "
            "before the same physical provider. Gateway and physical TTFT use the first non-empty delta.content "
            "from the same physical call. The paired difference includes relay overhead and is therefore a "
            "conservative upper bound; it is not a subtraction of independent p95 values."
        ),
        "config": {
            "path": "config/litellm_config.yaml",
            "sha256": hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        },
        "models": {},
    }
    docker_client = None
    temporary = None
    ownership: str | None = None
    relay_server = None
    relay_task = None
    relay_state = None
    records: list[dict[str, Any]] = []
    try:
        docker_client = docker.from_env()
        docker_client.ping()
        production = production_gateway(docker_client, production_port)
        production.reload()
        environment = provider_environment(production)
        bridge = docker_client.networks.get("bridge")
        bridge_ip = bridge.attrs["IPAM"]["Config"][0]["Gateway"]
        relay_port = free_port(bridge_ip)
        targets: dict[tuple[str, int], str] = {}
        for logical, prefix in PREFIXES.items():
            for slot in (1, 2):
                targets[(logical, slot)] = environment[f"{prefix}_{slot}_API_BASE"]
                environment[f"{prefix}_{slot}_API_BASE"] = f"http://{bridge_ip}:{relay_port}/{logical}/{slot}/v1"
        relay_state = RelayState(targets)
        relay_server = uvicorn.Server(
            uvicorn.Config(create_relay(relay_state), host=bridge_ip, port=relay_port, log_level="warning")
        )
        relay_task = asyncio.create_task(relay_server.serve())
        while not relay_server.started:
            if relay_task.done():
                await relay_task
            await asyncio.sleep(0.05)

        ownership = uuid.uuid4().hex
        temporary = await asyncio.to_thread(
            docker_client.containers.run,
            production.image.id,
            ["--config", "/app/config.yaml", "--port", "4000"],
            detach=True,
            ports={"4000/tcp": ("127.0.0.1", None)},
            extra_hosts={"host.docker.internal": "host-gateway"},
            volumes={str(CONFIG): {"bind": "/app/config.yaml", "mode": "ro"},
                     str(ROOT / "deploy/cloud_logging.py"): {"bind": "/app/cloud_logging.py", "mode": "ro"}},
            environment=environment,
            labels={OWNERSHIP_LABEL: ownership},
            security_opt=["no-new-privileges:true"],
            cap_drop=["ALL"],
        )
        temporary.reload()
        bindings = temporary.attrs["NetworkSettings"]["Ports"]["4000/tcp"]
        temporary_port = int(bindings[0]["HostPort"])
        base_url = f"http://127.0.0.1:{temporary_port}"
        await wait_ready(base_url)
        report["image"] = {
            "id": production.image.id,
            "repo_digests": production.image.attrs.get("RepoDigests", []),
            "same_image_id": temporary.image.id == production.image.id,
        }
        if not report["image"]["same_image_id"]:
            raise RuntimeError("ImageIdentityMismatch")

        async with httpx.AsyncClient(
            base_url=base_url, trust_env=False, timeout=600, follow_redirects=True
        ) as client:
            before = await client.get("/metrics/")
            before.raise_for_status()
            (run_dir / "prom-before.prom").write_text(before.text, encoding="utf-8")
            sample_failed = False
            for logical in selected_models:
                for _ in range(rounds):
                    record = await one_request(client, relay_state, logical)
                    records.append(record)
                    print(
                        json.dumps(
                            {
                                "logical_model": logical,
                                "index": len([item for item in records if item["logical_model"] == logical]),
                                "status": record["status"],
                                "error_class": record["error"],
                            }
                        ),
                        flush=True,
                    )
                    if record["status"] != "passed":
                        sample_failed = True
                        break
                if sample_failed:
                    break
            after = await client.get("/metrics/")
            after.raise_for_status()
            (run_dir / "prom-after.prom").write_text(after.text, encoding="utf-8")
            if sample_failed:
                raise RuntimeError("SampleFailed")

        write_csv(run_dir / "samples.csv", records)
        for logical in selected_models:
            samples = [record for record in records if record["logical_model"] == logical]
            overheads = [record["paired_overhead_ms"] for record in samples]
            p95 = percentile(overheads, 0.95)
            report["models"][logical] = {
                "samples": len(samples),
                "paired_overhead_p50_ms": percentile(overheads, 0.50),
                "paired_overhead_p95_ms": p95,
                "minimum_paired_overhead_ms": min(overheads),
                "maximum_paired_overhead_ms": max(overheads),
                "passed": p95 is not None and p95 <= 300,
            }
        report["result"] = "passed" if all(item["passed"] for item in report["models"].values()) else "failed"
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report
    except Exception as exc:
        if records:
            write_csv(run_dir / "samples.csv", records)
        report.update(result="failed", error=safe_error(exc), completed_at=datetime.now(timezone.utc).isoformat())
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        raise
    finally:
        cleanup_errors: list[str] = []
        if temporary is not None:
            try:
                temporary.reload()
            except Exception as exc:
                cleanup_errors.append(safe_error(exc))
            try:
                if temporary.labels.get(OWNERSHIP_LABEL) != ownership:
                    raise RuntimeError("TemporaryContainerOwnershipMismatch")
                await asyncio.to_thread(temporary.remove, force=True)
            except Exception as exc:
                cleanup_errors.append(safe_error(exc))
        if relay_server is not None:
            relay_server.should_exit = True
        if relay_task is not None:
            try:
                await relay_task
            except Exception as exc:
                cleanup_errors.append(safe_error(exc))
        if relay_state is not None:
            try:
                await relay_state.close()
            except Exception as exc:
                cleanup_errors.append(safe_error(exc))
        if docker_client is not None:
            try:
                docker_client.close()
            except Exception as exc:
                cleanup_errors.append(safe_error(exc))
        if cleanup_errors:
            report.update(
                result="failed",
                cleanup_errors=cleanup_errors,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--production-port", type=int, default=4001)
    parser.add_argument('--models', choices=LOGICAL_MODELS, nargs='+', default=LOGICAL_MODELS)
    args = parser.parse_args()
    try:
        result = asyncio.run(verify(args.rounds, args.production_port, args.models))
        print(json.dumps(result, indent=2))
        raise SystemExit(result["result"] != "passed")
    except Exception as exc:
        print(json.dumps({"result": "failed", "error": safe_error(exc)}))
        raise SystemExit(1)
