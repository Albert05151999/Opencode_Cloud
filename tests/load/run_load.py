#!/usr/bin/env python3
"""Bounded asyncio/HTTPX load client for gateway, OpenCode or model baselines."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import time
import uuid
from contextlib import suppress
from pathlib import Path

import httpx


class AssistantTokenObserver:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.assistants: set[str] = set()

    def observe(self, event: dict) -> bool:
        props = event.get("properties", {})
        if props.get("sessionID") != self.session_id:
            return False
        if event.get("type") == "message.updated":
            info = props.get("info", {})
            if info.get("role") == "assistant":
                self.assistants.add(info["id"])
        if event.get("type") == "message.part.delta":
            return props.get("messageID") in self.assistants and props.get("field") == "text" and bool(props.get("delta"))
        if event.get("type") == "message.part.updated":
            part = props.get("part", {})
            return part.get("messageID") in self.assistants and part.get("type") == "text" and bool(part.get("text"))
        return False


async def sse_events(response):
    """Parse event frames without retaining the whole connection."""
    lines = []
    size = 0
    async for line in response.aiter_lines():
        if not line:
            if lines:
                payload = "\n".join(lines)
                if payload != "[DONE]":
                    yield json.loads(payload)
            lines, size = [], 0
        elif line.startswith("data:"):
            value = line[5:].lstrip()
            size += len(value)
            if size > 1024 * 1024:
                raise ValueError("SSE frame exceeds 1 MiB")
            lines.append(value)


async def one_request(client, agent_id, username, logical_model, *, mode="gateway", timeout=120):
    record = dict(request_id="load_" + uuid.uuid4().hex, agent_id=agent_id, username=username, session_id=None, logical_model=logical_model, request_start=time.time(), sandbox_acquired_at=None, message_started_at=None, first_token_at=None, ttft_ms=None, completion_end=None, total_latency_ms=None, status="failed", error=None)
    started = time.perf_counter()
    first = None
    message_started = None
    task = None
    seen_sessions = set()
    headers = {"X-Cloud-Agent-ID": agent_id, "X-Cloud-Username": username, "X-Cloud-Request-ID": record["request_id"]}
    try:
        async with asyncio.timeout(timeout):
            if mode == "model":
                message_started = time.perf_counter()
                record["message_started_at"] = time.time()
                async with client.stream("POST", "/v1/chat/completions", json={"model": logical_model, "messages": [{"role": "user", "content": "Reply briefly: " + record["request_id"]}], "stream": True}) as response:
                    response.raise_for_status()
                    async for event in sse_events(response):
                        if any(choice.get("delta", {}).get("content") for choice in event.get("choices", [])) and first is None:
                            first = time.perf_counter()
                            record["first_token_at"] = time.time()
            else:
                body = {"title": record["request_id"]}
                if mode == "gateway":
                    body["_cloud"] = {"agent_id": agent_id, "username": username}
                response = await client.post("/session", json=body, headers=headers)
                response.raise_for_status()
                record["session_id"] = response.json()["id"]
                record["sandbox_acquired_at"] = time.time()
                observer = AssistantTokenObserver(record["session_id"])
                connected = asyncio.Event()
                token_seen = asyncio.Event()
                async def collect():
                    nonlocal first
                    async with client.stream("GET", "/event", headers=headers, timeout=None) as stream:
                        stream.raise_for_status()
                        # OpenCode emits server.connected immediately after subscription.
                        async for event in sse_events(stream):
                            props = event.get('properties', {})
                            for data in (props, props.get('info', {}), props.get('part', {})):
                                session = data.get('sessionID')
                                if session:
                                    seen_sessions.add(session)
                            connected.set()
                            if observer.observe(event) and first is None:
                                first = time.perf_counter()
                                record["first_token_at"] = time.time()
                                token_seen.set()
                task = asyncio.create_task(collect())
                wait_connected = asyncio.create_task(connected.wait())
                try:
                    done, _ = await asyncio.wait({task, wait_connected}, return_when=asyncio.FIRST_COMPLETED)
                    if task in done:
                        await task
                        raise RuntimeError("event stream ended before subscription")
                finally:
                    wait_connected.cancel()
                    with suppress(asyncio.CancelledError):
                        await wait_connected
                message_started = time.perf_counter()
                record["message_started_at"] = time.time()
                response = await client.post(f"/session/{record['session_id']}/message", headers=headers, json={"model": {"providerID": "cloud-model-gateway", "modelID": logical_model}, "parts": [{"type": "text", "text": "Reply briefly: " + record["request_id"]}]})
                response.raise_for_status()
                if response.json().get("info", {}).get("error"):
                    raise RuntimeError("OpenCode returned a model error")
                await asyncio.wait_for(token_seen.wait(), timeout=5)
            if first is None:
                raise RuntimeError("no assistant model token observed")
            record["ttft_ms"] = (first - message_started) * 1000
            record["request_ttft_ms"] = (first - started) * 1000
            record["status"] = "passed"
    except Exception as exc:
        # Do not persist provider response bodies or authentication headers.
        record["error"] = type(exc).__name__
    finally:
        if first is not None and message_started is not None:
            record["ttft_ms"] = (first - message_started) * 1000
            record["request_ttft_ms"] = (first - started) * 1000
        record["completion_end"] = time.time()
        record["total_latency_ms"] = (time.perf_counter() - started) * 1000
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        record['sse_session_ids'] = sorted(seen_sessions)
    return record


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


async def run(base_url, *, rounds=1, mode="gateway", output=Path("artifacts/perf/load"), timeout=120, matrix=None):
    if rounds < 1:
        raise ValueError("rounds must be positive")
    matrix = matrix or [(agent, user, model) for agent, models in [("agent-code", ("coding-fast", "coding-quality")), ("agent-data", ("data-fast", "data-quality"))] for user in ("alice", "bob") for model in models]
    records = []
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), trust_env=False, timeout=timeout) as client:
        for _ in range(rounds):
            records.extend(await asyncio.gather(*(one_request(client, *item, mode=mode, timeout=timeout) for item in matrix)))
    summary = {"mode": mode, "rounds": rounds, "request_count": len(records), "failures": sum(record["status"] != "passed" for record in records), "ttft_ms": {str(p): percentile([r["ttft_ms"] for r in records if r["ttft_ms"] is not None], p) for p in (0.5, 0.95)}, "total_latency_ms": {str(p): percentile([r["total_latency_ms"] for r in records], p) for p in (0.5, 0.95)}, "sandbox_acquired_at_semantics": "Client-observed session response time; upper bound, not server-side timestamp", "ttft_semantics": "First assistant content since message POST; request_ttft_ms also includes session creation and SSE subscription"}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".json").write_text(json.dumps({"summary": summary, "requests": records}, indent=2) + "\n")
    fields = sorted({key for record in records for key in record})
    with output.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--mode", choices=("gateway", "opencode", "model"), default="gateway")
    parser.add_argument("--output", type=Path, default=Path("artifacts/perf/load"))
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    summary = asyncio.run(run(args.base_url, rounds=args.rounds, mode=args.mode, output=args.output, timeout=args.timeout))
    print(json.dumps(summary, indent=2))
    raise SystemExit(bool(summary["failures"]))
