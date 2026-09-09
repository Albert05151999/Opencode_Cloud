#!/usr/bin/env python3
"""Measure guarded sandbox resource capacity with a private real backend."""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import shutil
import tempfile
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable

import httpx

from app.config import load_config
from app.main import build_app


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "perf" / "resource-capacity"
INSTANCE = "stage30-resource"
TIERS = (10, 20, 50)
RESERVE_BYTES = 3 * 1024**3
POLL_SECONDS = 0.10


def meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        name, _, raw = line.partition(":")
        fields = raw.split()
        if fields:
            values[name] = int(fields[0]) * (1024 if len(fields) > 1 and fields[1] == "kB" else 1)
    for required in ("MemAvailable", "SwapFree", "SwapTotal"):
        if required not in values:
            raise RuntimeError(f"/proc/meminfo lacks {required}")
    return {
        "mem_available_bytes": values["MemAvailable"],
        "swap_free_bytes": values["SwapFree"],
        "swap_total_bytes": values["SwapTotal"],
    }


def memory_events() -> dict[str, int] | None:
    path = Path("/sys/fs/cgroup/memory.events")
    if not path.is_file():
        return None
    result: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        name, value = line.split()
        result[name] = int(value)
    return result


def oom_delta(before: dict[str, int] | None, after: dict[str, int] | None) -> dict[str, int] | None:
    if before is None or after is None:
        return None
    return {name: after.get(name, 0) - before.get(name, 0) for name in ("oom", "oom_kill")}


def tree_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_size
        except FileNotFoundError:
            pass
    return total


def per_user_storage(directory: Path, count: int) -> list[dict[str, Any]]:
    return [
        {
            "username": f"capacity-{index:03d}",
            "workspace_bytes": tree_size(directory / "workspaces" / "agent-code" / f"capacity-{index:03d}"),
            "state_bytes": tree_size(directory / "state" / "agent-code" / f"capacity-{index:03d}"),
        }
        for index in range(count)
    ]


def inspect_with_size(container: Any) -> dict[str, Any]:
    api = container.client.api
    response = api._get(api._url("/containers/{0}/json", container.id), params={"size": True})
    return api._result(response, json=True)


def container_memory_events(container: Any, pid: int) -> dict[str, Any]:
    memberships = Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8").splitlines()
    unified = next((line.split(":", 2)[2] for line in memberships if line.startswith("0::")), None)
    path = Path("/sys/fs/cgroup") / (unified or "").lstrip("/") / "memory.events"
    if unified is not None and path.is_file():
        values = dict(line.split() for line in path.read_text(encoding="utf-8").splitlines())
        return {"version": 2, **{key: int(value) for key, value in values.items()}}
    memory_path = next(
        (line.split(":", 2)[2] for line in memberships if "memory" in line.split(":", 2)[1].split(",")),
        None,
    )
    if memory_path is None:
        raise RuntimeError("container has no memory cgroup membership")
    root = Path("/sys/fs/cgroup/memory") / memory_path.lstrip("/")
    result: dict[str, Any] = {
        "version": 1,
        "failcnt": int((root / "memory.failcnt").read_text(encoding="utf-8").strip()),
    }
    for line in (root / "memory.oom_control").read_text(encoding="utf-8").splitlines():
        name, value = line.split()
        result[name] = int(value)
    return result


def assert_no_container_oom(sample: dict[str, Any]) -> None:
    events = sample["cgroup_memory_events"]
    failed = sample["oom_killed"] or (
        events["version"] == 2 and (events.get("oom", 0) or events.get("oom_kill", 0))
    ) or (events["version"] == 1 and (events.get("failcnt", 0) or events.get("under_oom", 0) or events.get("oom_kill", 0)))
    if failed:
        raise RuntimeError(f"container memory cgroup reported pressure/OOM: {events}")


def container_resources(container: Any, expected: Any | None = None) -> dict[str, Any]:
    stats = container.stats(stream=False, one_shot=True)
    memory = stats.get("memory_stats") or {}
    usage = int(memory.get("usage", 0))
    details = memory.get("stats") or {}
    cache_source = next(
        (name for name in ("total_inactive_file", "inactive_file", "cache") if name in details), None
    )
    if cache_source is None:
        raise RuntimeError("Docker memory stats lack a supported cache field")
    cache = int(details[cache_source])
    working_set = max(0, usage - cache)
    container.reload()
    pid = int((container.attrs.get("State") or {}).get("Pid") or 0)
    rss: int | None = None
    status = Path(f"/proc/{pid}/status")
    if pid and status.is_file():
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                rss = int(line.split()[1]) * 1024
                break
    inspected = inspect_with_size(container)
    host_config = inspected.get("HostConfig") or {}
    limits = {
        "memory_bytes": int(host_config.get("Memory") or 0),
        "nano_cpus": int(host_config.get("NanoCpus") or 0),
        "pids_limit": int(host_config.get("PidsLimit") or 0),
    }
    if expected is not None:
        wanted = {
            "memory_bytes": expected.memory_mb * 1024**2,
            "nano_cpus": int(expected.cpu_limit * 1_000_000_000),
            "pids_limit": expected.pids_limit,
        }
        if limits != wanted:
            raise RuntimeError(f"container resource limits differ from Agent definition: {limits}")
    return {
        "container_id": container.id,
        "memory_usage_bytes": usage,
        "memory_cache_bytes": cache,
        "memory_cache_source": cache_source,
        "memory_working_set_bytes": working_set,
        "pid1_rss_bytes": rss,
        "cgroup_rss_bytes": int(details.get("total_rss", details.get("rss", details.get("anon", 0)))),
        "size_rw_bytes": int(inspected.get("SizeRw") or 0),
        "size_root_fs_bytes": int(inspected.get("SizeRootFs") or 0),
        "host_config_limits": limits,
        "oom_killed": bool((inspected.get("State") or {}).get("OOMKilled")),
        "cgroup_memory_events": container_memory_events(container, pid),
    }


async def observe_while(
    operation: Awaitable[Any], container: Any | None = None, expected: Any | None = None,
) -> tuple[Any, dict[str, Any]]:
    task = asyncio.ensure_future(operation)
    baseline = meminfo()
    minimum_available = baseline["mem_available_bytes"]
    minimum_swap_free = baseline["swap_free_bytes"]
    maximum_working_set = 0
    samples = 0
    try:
        while not task.done():
            current = meminfo()
            minimum_available = min(minimum_available, current["mem_available_bytes"])
            minimum_swap_free = min(minimum_swap_free, current["swap_free_bytes"])
            if (
                current["mem_available_bytes"] < RESERVE_BYTES
                or current["swap_free_bytes"] < baseline["swap_free_bytes"]
            ):
                raise RuntimeError("memory reserve or swap guard breached during operation")
            if container is not None:
                sample = await asyncio.to_thread(container_resources, container, expected)
                assert_no_container_oom(sample)
                maximum_working_set = max(maximum_working_set, sample["memory_working_set_bytes"])
            samples += 1
            await asyncio.sleep(POLL_SECONDS)
        result = await task
    except BaseException:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        raise
    minimum_available = min(minimum_available, meminfo()["mem_available_bytes"])
    return result, {
        "poll_samples": samples,
        "minimum_mem_available_bytes": minimum_available,
        "minimum_swap_free_bytes": minimum_swap_free,
        "maximum_observed_working_set_bytes": maximum_working_set,
    }


def capacity_projection(current: int, target: int, estimate: int) -> dict[str, Any]:
    available = meminfo()["mem_available_bytes"]
    required = RESERVE_BYTES + max(0, target - current) * estimate
    return {
        "current_sandboxes": current,
        "target_sandboxes": target,
        "estimated_bytes_per_next_sandbox": estimate,
        "mem_available_bytes": available,
        "required_available_bytes": required,
        "reserve_bytes": RESERVE_BYTES,
        "safe_to_continue": available >= required,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Resource capacity verification", "", f"Result: **{report['result']}**", "",
        f"Instance: `{INSTANCE}`", "", "LSP/MCP capacity measurement: **N/A** (disabled by agent/runtime configuration).", "",
        "| Tier | Result | Sandboxes | MemAvailable | SwapFree |",
        "|---:|---|---:|---:|---:|",
    ]
    for tier in report.get("tiers", []):
        resources = tier.get("resources", {})
        lines.append(
            f"| {tier['target']} | {tier['result']} | {tier.get('sandboxes', 0)} | "
            f"{resources.get('mem_available_bytes', 'N/A')} | {resources.get('swap_free_bytes', 'N/A')} |"
        )
    if report.get("recommendation"):
        lines += ["", "## Recommendation", "", report["recommendation"]]
    if report.get("error"):
        lines += ["", "## Error", "", f"`{report['error']}`"]
    return "\n".join(lines) + "\n"


async def verify() -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    report: dict[str, Any] = {
        "result": "running",
        "started_at": started.isoformat(),
        "instance_id": INSTANCE,
        "tiers": [],
        "reserve_bytes": RESERVE_BYTES,
        "lsp_mcp": {"status": "N/A", "reason": "downloads/default plugins are disabled; no configured LSP/MCP workload"},
    }
    cleanup_errors: list[str] = []
    backend = None
    monitor = None
    app = None
    temporary = tempfile.TemporaryDirectory(prefix="cloud-stage30-")
    directory = Path(temporary.name)
    initial_host = meminfo()
    initial_events = memory_events()
    report["host_before"] = {**initial_host, "memory_events": initial_events}
    if initial_host["swap_free_bytes"] != initial_host["swap_total_bytes"]:
        report.update(result="failed", error="Swap is already in use; refusing capacity verification")
    endpoints: list[Any] = []
    containers: list[Any] = []
    try:
        if report["result"] == "failed":
            raise RuntimeError(report["error"])
        shutil.copytree(ROOT / "agents", directory / "agents")
        config = load_config(ROOT / "config.cfg")
        config = replace(
            config,
            platform=replace(config.platform, data_root=str(directory), instance_id=INSTANCE),
            storage=replace(
                config.storage,
                workspace_root=str(directory / "workspaces"),
                state_root=str(directory / "state"),
            ),
        )
        app = build_app(config, directory / "agents")
        backend = app.state.backend
        monitor = app.state.health_monitor
        if initial_host["mem_available_bytes"] < RESERVE_BYTES + 768 * 1024**2:
            raise RuntimeError("insufficient memory for even the guarded baseline")
        image = await asyncio.to_thread(backend.client.images.get, config.sandbox.image)
        agent_resources = backend.agent_catalog.load("agent-code").resources
        report["image"] = {
            "id": image.id,
            "size_bytes": int(image.attrs.get("Size") or 0),
            "repo_digests": image.attrs.get("RepoDigests") or [],
            "rootfs_layers": (image.attrs.get("RootFS") or {}).get("Layers") or [],
        }

        first_before = meminfo()["mem_available_bytes"]
        endpoint, startup = await observe_while(
            backend.acquire("agent-code", "capacity-000")
        )
        async with httpx.AsyncClient(trust_env=False, timeout=30) as native:
            (await native.get(endpoint.base_url + "/session/status")).raise_for_status()
        endpoints.append(endpoint)
        await backend.release(endpoint)
        first_container = backend.client.containers.get(endpoint.container_id)
        containers.append(first_container)
        first_resources = await asyncio.to_thread(container_resources, first_container, agent_resources)
        startup_drop = max(0, first_before - startup["minimum_mem_available_bytes"])
        assert_no_container_oom(first_resources)
        estimate = math.ceil(max(first_resources["memory_working_set_bytes"], startup_drop, 512 * 1024**2) * 1.5)
        report["baseline_sandbox"] = {
            **first_resources,
            "startup": startup,
            "startup_mem_available_drop_bytes": startup_drop,
        }

        for target in TIERS:
            projection = capacity_projection(len(containers), target, estimate)
            tier: dict[str, Any] = {"target": target, "projection": projection}
            if not projection["safe_to_continue"]:
                tier.update(result="skipped_capacity_guard", sandboxes=len(containers), resources=meminfo())
                report["tiers"].append(tier)
                print(json.dumps({"tier": target, "result": tier["result"], "sandboxes": len(containers)}), flush=True)
                for later in TIERS[TIERS.index(target) + 1:]:
                    report["tiers"].append({
                        "target": later, "result": "skipped_after_capacity_guard",
                        "sandboxes": len(containers), "resources": meminfo(),
                    })
                break
            tier_events_before = memory_events()
            minimum_available = meminfo()["mem_available_bytes"]
            while len(containers) < target:
                if meminfo()["mem_available_bytes"] < RESERVE_BYTES + estimate:
                    raise RuntimeError("memory reserve reached during guarded tier creation")
                index = len(containers)
                before = meminfo()["mem_available_bytes"]
                endpoint, observed = await observe_while(
                    backend.acquire("agent-code", f"capacity-{index:03d}")
                )
                async with httpx.AsyncClient(trust_env=False, timeout=30) as native:
                    (await native.get(endpoint.base_url + "/session/status")).raise_for_status()
                endpoints.append(endpoint)
                await backend.release(endpoint)
                container = backend.client.containers.get(endpoint.container_id)
                containers.append(container)
                resources = await asyncio.to_thread(container_resources, container, agent_resources)
                assert_no_container_oom(resources)
                startup_drop = max(0, before - observed["minimum_mem_available_bytes"])
                estimate = max(
                    estimate,
                    math.ceil(max(resources["memory_working_set_bytes"], startup_drop, 512 * 1024**2) * 1.5),
                )
                minimum_available = min(minimum_available, observed["minimum_mem_available_bytes"])
            samples = [
                await asyncio.to_thread(container_resources, item, agent_resources)
                for item in containers
            ]
            for sample in samples:
                assert_no_container_oom(sample)
            events_after = memory_events()
            delta = oom_delta(tier_events_before, events_after)
            if delta and any(delta.values()):
                raise RuntimeError(f"cgroup OOM event detected at tier {target}: {delta}")
            tier.update(
                result="passed", sandboxes=len(containers), resources=meminfo(),
                minimum_mem_available_bytes=minimum_available,
                cgroup_memory_events=events_after, oom_delta=delta,
                aggregate_working_set_bytes=sum(item["memory_working_set_bytes"] for item in samples),
                maximum_sandbox_working_set_bytes=max(item["memory_working_set_bytes"] for item in samples),
                aggregate_size_rw_bytes=sum(item["size_rw_bytes"] for item in samples),
                container_samples=samples,
            )
            report["tiers"].append(tier)
            print(json.dumps({"tier": target, "result": tier["result"], "sandboxes": tier["sandboxes"]}), flush=True)

        if not containers:
            raise RuntimeError("no sandbox available for active request measurement")
        active = containers[0]
        print(json.dumps({"phase": "active_model_request", "sandboxes": len(containers)}), flush=True)
        active_before = await asyncio.to_thread(container_resources, active, agent_resources)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://controller.test", timeout=600
        ) as api:
            created = await api.post("/session", json={"_cloud": {"agent_id": "agent-code", "username": "capacity-000"}})
            created.raise_for_status()
            session_id = created.json()["id"]
            request = api.post(
                f"/session/{session_id}/message",
                json={
                    "model": {"providerID": "cloud-model-gateway", "modelID": "coding-fast"},
                    "parts": [{"type": "text", "text": "Reply with one short sentence."}],
                },
            )
            response, active_observed = await observe_while(request, active, agent_resources)
            response.raise_for_status()
            payload = response.json()
            info = payload.get("info") or {}
            text = "".join(
                part.get("text", "") for part in payload.get("parts", []) if part.get("type") == "text"
            )
            if info.get("error") or info.get("modelID") != "coding-fast" or not text.strip():
                raise RuntimeError("active request returned an error, wrong model, or empty text")
        active_after = await asyncio.to_thread(container_resources, active, agent_resources)
        assert_no_container_oom(active_after)
        report["active_request"] = {
            "status_code": response.status_code,
            "model": "coding-fast",
            "response_model": info.get("modelID"),
            "response_text_present": bool(text.strip()),
            "timeout_seconds": 600,
            "before": active_before,
            "peak": active_observed,
            "after": active_after,
        }

        storage_before_cleanup = {
            "workspace_bytes": tree_size(directory / "workspaces"),
            "state_bytes": tree_size(directory / "state"),
            "per_user_growth_from_empty_bytes": per_user_storage(directory, len(containers)),
        }
        if any(p.is_dir() for p in (directory / "state").rglob(".npm")):
            raise RuntimeError("unexpected runtime npm download cache in persistent state")
        markers: list[tuple[Path, str]] = []
        for index in range(len(containers)):
            for kind in ("workspaces", "state"):
                base = directory / kind / "agent-code" / f"capacity-{index:03d}"
                marker = base / "stage30-retained.marker"
                marker.write_text(f"{kind}-{index}", encoding="utf-8")
                markers.append((marker, f"{kind}-{index}"))
        future = datetime.now(timezone.utc) + timedelta(
            seconds=max(config.sandbox.idle_timeout_seconds, 1800) + 60
        )
        report["image"]["all_container_image_ids_match"] = all(
            inspect_with_size(container).get("Image") == image.id for container in containers
        )
        if not report["image"]["rootfs_layers"] or not report["image"]["all_container_image_ids_match"]:
            raise RuntimeError("containers do not prove shared pinned image layers")
        print(json.dumps({"phase": "idle_cleanup", "sandboxes": len(containers)}), flush=True)
        cleanup_started = time.perf_counter()
        await monitor.tick(now=future)
        cleanup_seconds = time.perf_counter() - cleanup_started
        remaining = backend.client.containers.list(all=True, filters={"label": f"cloud.platform_instance={INSTANCE}"})
        if remaining:
            raise RuntimeError(f"idle monitor left {len(remaining)} test containers")
        storage_after_cleanup = {
            "workspace_bytes": tree_size(directory / "workspaces"),
            "state_bytes": tree_size(directory / "state"),
            "per_user_growth_from_empty_bytes": per_user_storage(directory, len(containers)),
        }
        if not (directory / "workspaces").exists() or not (directory / "state").exists():
            raise RuntimeError("idle cleanup removed persistent roots")
        if any(path.read_text(encoding="utf-8") != value for path, value in markers):
            raise RuntimeError("persistent workspace/state marker did not survive idle cleanup")
        with backend.registry.connect() as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"registry integrity check failed: {integrity}")
        host_after_cleanup = meminfo()
        report["idle_cleanup"] = {
            "duration_seconds": cleanup_seconds,
            "future_tick": future.isoformat(),
            "containers_remaining": 0,
            "storage_before": storage_before_cleanup,
            "storage_after": storage_after_cleanup,
            "storage_byte_change": {
                key: storage_after_cleanup[key] - storage_before_cleanup[key]
                for key in ("workspace_bytes", "state_bytes")
            },
            "registry_integrity_check": integrity,
            "host_after": host_after_cleanup,
            "mem_available_released_bytes": host_after_cleanup["mem_available_bytes"]
            - report["tiers"][-1]["resources"]["mem_available_bytes"],
        }
        report["recommendation"] = (
            f"Observed up to {len(containers)} sandboxes. Keep at least 3 GiB MemAvailable and reserve "
            f"{estimate} measured bytes for each additional sandbox before raising production concurrency."
        )
        final_events = memory_events()
        total_oom = oom_delta(initial_events, final_events)
        if total_oom and any(total_oom.values()):
            raise RuntimeError(f"cgroup OOM event detected during verification: {total_oom}")
        report["host_after"] = {**host_after_cleanup, "memory_events": final_events, "oom_delta": total_oom}
        report["result"] = "passed"
    except Exception as exc:
        report.update(result="failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        if backend is not None:
            try:
                owned = backend.client.containers.list(
                    all=True, filters={"label": f"cloud.platform_instance={INSTANCE}"}
                )
                for container in owned:
                    if container.labels.get("cloud.platform_instance") != INSTANCE:
                        raise RuntimeError("container ownership mismatch")
                    await asyncio.to_thread(container.remove, force=True)
                leftovers = backend.client.containers.list(
                    all=True, filters={"label": f"cloud.platform_instance={INSTANCE}"}
                )
                if leftovers:
                    raise RuntimeError(f"{len(leftovers)} owned containers remain")
            except Exception as exc:
                cleanup_errors.append(f"{type(exc).__name__}: {exc}")
            try:
                await monitor.client.aclose()
            except Exception as exc:
                cleanup_errors.append(f"{type(exc).__name__}: {exc}")
            try:
                backend.client.close()
            except Exception as exc:
                cleanup_errors.append(f"{type(exc).__name__}: {exc}")
        if cleanup_errors:
            report["cleanup_errors"] = cleanup_errors
            report["result"] = "failed"
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (OUTPUT / "report.md").write_text(markdown(report), encoding="utf-8")
        temporary.cleanup()
    return report


def main() -> None:
    argparse.ArgumentParser().parse_args()
    report = asyncio.run(verify())
    print(json.dumps(report, indent=2))
    raise SystemExit(report["result"] != "passed")


if __name__ == "__main__":
    main()
