#!/usr/bin/env python3
"""Measure real cold/warm API latency without invoking a model."""

import argparse
import concurrent.futures
import json
import math
import statistics
import time
import uuid
from pathlib import Path

import httpx


def headers(token, agent, username):
    trace_id = uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]
    return {
        "Authorization": f"Bearer {token}",
        "x-cloud-agent-id": agent,
        "x-cloud-username": username,
        "x-cloud-request-id": uuid.uuid4().hex,
        "traceparent": f"00-{trace_id}-{span_id}-01",
    }


def measured(client, token, agent, username, method, path, **kwargs):
    request_headers = headers(token, agent, username)
    request = client.build_request(
        method, path, headers=request_headers, **kwargs
    )
    started = time.perf_counter()
    response = client.send(request, stream=True)
    ttfb = time.perf_counter() - started
    body = response.read()
    total = time.perf_counter() - started
    status = response.status_code
    response.close()
    if status >= 400:
        raise RuntimeError(f"{method} {path} returned HTTP {status}")
    return {
        "status": status,
        "ttfb_ms": round(ttfb * 1000, 3),
        "total_ms": round(total * 1000, 3),
        "response_bytes": len(body),
        "request_id": request_headers["x-cloud-request-id"],
        "trace_id": request_headers["traceparent"].split("-")[1],
        "json": json.loads(body) if body else None,
    }


def summary(rows):
    def values(key):
        return sorted(row[key] for row in rows)

    def percentile(items, fraction):
        if len(items) == 1:
            return items[0]
        position = (len(items) - 1) * fraction
        low, high = math.floor(position), math.ceil(position)
        return items[low] + (items[high] - items[low]) * (position - low)

    result = {"count": len(rows)}
    for key in ("ttfb_ms", "total_ms"):
        items = values(key)
        result[key] = {
            "p50": round(statistics.median(items), 3),
            "p95": round(percentile(items, 0.95), 3),
            "max": round(max(items), 3),
        }
    return result


def request_json(client, token, method, path, **kwargs):
    response = client.request(method, path, headers=headers(token, "agent-code", "perf-control"), **kwargs)
    response.raise_for_status()
    return response.json()


def poll_job(client, token, job):
    job_id = job.get("id") or job.get("job_id")
    if not job_id:
        raise RuntimeError("sandbox stop returned no job id")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        current = request_json(client, token, "GET", f"/cloud/admin/jobs/{job_id}")
        if current["status"] == "succeeded":
            return job_id
        if current["status"] in {"failed", "cancelled", "interrupted", "needs_recovery"}:
            raise RuntimeError(f"sandbox stop ended with {current['status']}")
        time.sleep(0.25)
    raise TimeoutError("sandbox stop timed out")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="before")
    parser.add_argument("--url", default="http://127.0.0.1:18080")
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--output-dir", default="artifacts/verification/performance")
    args = parser.parse_args()
    token = Path(args.token_file).read_text().strip()
    if not token:
        parser.error("token file is empty")
    username = f"perf-{args.label}-{uuid.uuid4().hex[:12]}"
    agent = "agent-code"
    output = Path(args.output_dir) / f"{args.label}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "label": args.label,
        "target": args.url,
        "agent_id": agent,
        "username": username,
        "cold_target_ms": 4000,
        "warm_target_ms": 300,
    }
    sandbox_id = None
    with httpx.Client(base_url=args.url, timeout=180, trust_env=False) as client:
        try:
            cold = measured(client, token, agent, username, "GET", "/global/health")
            sample_fields = ("status", "ttfb_ms", "total_ms", "response_bytes", "request_id", "trace_id")
            report["cold"] = {key: cold[key] for key in sample_fields}
            serial = [measured(client, token, agent, username, "GET", "/global/health") for _ in range(20)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                concurrent_rows = list(pool.map(lambda _: measured(client, token, agent, username, "GET", "/global/health"), range(8)))
            sessions_before = measured(client, token, agent, username, "GET", "/session")
            created = measured(client, token, agent, username, "POST", "/session", json={"title": "Performance baseline"})
            session_id = created["json"]["id"]
            messages = [measured(client, token, agent, username, "GET", f"/session/{session_id}/message") for _ in range(10)]
            report.update({
                "warm_serial": {**summary(serial), "samples": [{key: row[key] for key in sample_fields} for row in serial]},
                "warm_concurrent_4": {**summary(concurrent_rows), "samples": [{key: row[key] for key in sample_fields} for row in concurrent_rows]},
                "sessions_list": {key: sessions_before[key] for key in sample_fields},
                "session_create": {key: created[key] for key in sample_fields},
                "bound_messages": {**summary(messages), "samples": [{key: row[key] for key in sample_fields} for row in messages]},
                "targets": {
                    "cold_total_under_4000ms": cold["total_ms"] < 4000,
                    "warm_serial_total_p95_under_300ms": summary(serial)["total_ms"]["p95"] < 300,
                    "warm_concurrent_total_p95_under_300ms": summary(concurrent_rows)["total_ms"]["p95"] < 300,
                    "bound_messages_total_p95_under_300ms": summary(messages)["total_ms"]["p95"] < 300,
                    "warm_serial_total_max_under_300ms": summary(serial)["total_ms"]["max"] < 300,
                    "warm_concurrent_total_max_under_300ms": summary(concurrent_rows)["total_ms"]["max"] < 300,
                    "bound_messages_total_max_under_300ms": summary(messages)["total_ms"]["max"] < 300,
                },
            })
        finally:
            try:
                listing = request_json(client, token, "GET", "/cloud/admin/sandboxes", params={"q": username})
                row = next((item for item in listing.get("items", []) if item.get("username") == username and item.get("agent_id") == agent), None)
                if row:
                    sandbox_id = row.get("sandbox_id") or row.get("id")
                    job = request_json(client, token, "POST", f"/cloud/admin/sandboxes/{sandbox_id}/stop", json={"request_id": uuid.uuid4().hex})
                    report["cleanup"] = {"sandbox_stopped": True, "job_id": poll_job(client, token, job)}
                else:
                    report["cleanup"] = {"sandbox_stopped": False, "reason": "sandbox not found"}
            finally:
                output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"output": str(output), "username": username, "targets": report.get("targets"), "cleanup": report.get("cleanup")}))


if __name__ == "__main__":
    main()
