"""Per-application Prometheus collectors and streaming-safe ASGI middleware."""

from __future__ import annotations

import time
import os
import shutil
from pathlib import Path

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily


class HostCollector:
    """Linux host counters used by the optional dashboard; no per-user labels."""

    def collect(self):
        if not Path("/proc/stat").is_file():
            return
        values = Path("/proc/stat").read_text().splitlines()[0].split()[1:9]
        cpu = CounterMetricFamily(
            "cloud_host_cpu_seconds", "Aggregate Linux CPU time", labels=["mode"]
        )
        for mode, value in zip(
            ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal"),
            values,
        ):
            cpu.add_metric([mode], int(value) / os.sysconf("SC_CLK_TCK"))
        yield cpu
        memory = {
            line.split(":")[0]: int(line.split()[1]) * 1024
            for line in Path("/proc/meminfo").read_text().splitlines()
            if line.startswith(("MemTotal:", "MemAvailable:"))
        }
        yield GaugeMetricFamily(
            "cloud_host_memory_total_bytes",
            "Linux total memory",
            value=memory["MemTotal"],
        )
        yield GaugeMetricFamily(
            "cloud_host_memory_available_bytes",
            "Linux available memory",
            value=memory["MemAvailable"],
        )
        disk = shutil.disk_usage("/")
        yield GaugeMetricFamily(
            "cloud_host_disk_total_bytes", "Root filesystem capacity", value=disk.total
        )
        yield GaugeMetricFamily(
            "cloud_host_disk_free_bytes", "Root filesystem free bytes", value=disk.free
        )


def route_label(path: str) -> str:
    fixed = {
        "/session",
        "/session/status",
        "/event",
        "/global/event",
        "/global/health",
        "/file",
        "/file/content",
        "/mcp",
        "/provider",
        "/config",
        "/cloud/health",
        "/cloud/health/ready",
        "/cloud/files/upload",
        "/cloud/files/download",
        "/cloud/files/list",
        "/metrics",
    }
    if path in fixed:
        return path
    parts = path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "session" and parts[1].startswith("ses_"):
        if len(parts) == 2:
            return "/session/:id"
        if len(parts) == 3 and parts[2] in {
            "message",
            "abort",
            "fork",
            "diff",
            "todo",
            "summarize",
        }:
            return "/session/:id/" + parts[2]
        if len(parts) == 4 and parts[2] == "message":
            return "/session/:id/message/:id"
    return "other"


class PlatformMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.registry.register(HostCollector())

        def counter(name, description, labels=()):
            return Counter(name, description, labels, registry=self.registry)

        def gauge(name, description):
            return Gauge(name, description, registry=self.registry)

        def histogram(name, description, labels=()):
            return Histogram(name, description, labels, registry=self.registry)

        self.http_requests = counter(
            "cloud_http_requests_total",
            "Completed HTTP requests",
            ("method", "route", "status"),
        )
        self.http_errors = counter(
            "cloud_http_errors_total",
            "Failed HTTP requests",
            ("method", "route", "status"),
        )
        self.http_duration = histogram(
            "cloud_request_duration_seconds",
            "HTTP lifetime including streamed body",
            ("method", "route"),
        )
        self.sse_active = gauge("cloud_sse_connections", "Open SSE connections")
        self.sse_duration = histogram(
            "cloud_sse_connection_duration_seconds", "SSE connection lifetime"
        )
        self.route_lookup = histogram(
            "cloud_route_lookup_duration_seconds", "Route metadata lookup time"
        )
        self.sandbox_active = gauge("sandbox_active", "Ready sandboxes in registry")
        self.sandbox_starting = gauge(
            "sandbox_starting", "In-progress sandbox acquisitions"
        )
        self.sandbox_create = histogram(
            "sandbox_create_seconds", "Docker container creation time"
        )
        self.sandbox_start = histogram(
            "sandbox_start_seconds", "Docker container start time"
        )
        self.sandbox_ready = histogram(
            "sandbox_ready_seconds", "Time waiting for OpenCode readiness"
        )
        self.sandbox_cold_start = histogram(
            "sandbox_cold_start_seconds", "New sandbox acquisition through readiness"
        )
        self.sandbox_reuse = counter("sandbox_reuse_total", "Reused sandboxes")
        self.sandbox_created = counter(
            "sandbox_create_total", "Created Docker containers"
        )
        self.sandbox_failures = counter(
            "sandbox_start_failures_total", "Failed sandbox acquisitions"
        )
        self.sandbox_health_failures = counter(
            "sandbox_health_failures_total", "Failed background health checks"
        )
        self.sandbox_evictions = counter(
            "sandbox_idle_evictions_total", "Idle sandboxes stopped"
        )
        self.model_health = gauge(
            "model_gateway_healthy",
            "Last gateway health result: -1 unknown, 0 unhealthy, 1 healthy",
        )
        self.model_health.set(-1)
        self.upload_bytes = counter(
            "workspace_upload_bytes_total", "Bytes successfully committed by uploads"
        )
        self.download_bytes = counter(
            "workspace_download_bytes_total", "Download body bytes sent"
        )

    def render(self) -> bytes:
        return generate_latest(self.registry)


class MetricsMiddleware:
    def __init__(self, app, metrics: PlatformMetrics) -> None:
        self.app, self.metrics = app, metrics

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = time.perf_counter()
        route = route_label(scope["path"])
        method = (
            scope["method"]
            if scope["method"]
            in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
            else "OTHER"
        )
        status = 500
        sse = False

        async def measured_send(message):
            nonlocal status, sse
            await send(message)
            if message["type"] == "http.response.start":
                status = message["status"]
                content_type = dict(message.get("headers", [])).get(
                    b"content-type", b""
                )
                sse = content_type.startswith(b"text/event-stream")
                if sse:
                    self.metrics.sse_active.inc()
            elif (
                message["type"] == "http.response.body"
                and route == "/cloud/files/download"
                and status == 200
            ):
                self.metrics.download_bytes.inc(len(message.get("body", b"")))

        try:
            await self.app(scope, receive, measured_send)
        finally:
            elapsed = time.perf_counter() - started
            labels = (method, route, str(status))
            self.metrics.http_requests.labels(*labels).inc()
            if status >= 400:
                self.metrics.http_errors.labels(*labels).inc()
            self.metrics.http_duration.labels(method, route).observe(elapsed)
            if sse:
                self.metrics.sse_active.dec()
                self.metrics.sse_duration.observe(elapsed)
