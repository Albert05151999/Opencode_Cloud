"""Construct the Docker backend's typed configuration from its module input."""

import os
from pathlib import Path
from shared_libs.config_models import (
    AppConfig,
    PlatformConfig,
    AuthConfig,
    SandboxConfig,
    StorageConfig,
    OpenCodeConfig,
    ModelGatewayConfig,
    MetricsConfig,
    PerformanceConfig,
    LoadCapacityConfig,
)


def backend_config(config):
    values = config.get("settings", {})
    supplied = values.get("controller_config", {})

    def section(name, cls, default):
        return cls(**{**default, **supplied.get(name, {})})

    result = AppConfig(
        section(
            "platform",
            PlatformConfig,
            dict(
                instance_id="opencode-cloud",
                host="0.0.0.0",
                port=config["port"],
                log_level="INFO",
                data_root=config["data_root"],
            ),
        ),
        section(
            "auth",
            AuthConfig,
            dict(
                enabled=False,
                jwt_header="Authorization",
                jwt_algorithm="HS256",
                jwt_issuer="opencode-cloud",
                cookie_token_endpoint="/cloud/auth/token",
            ),
        ),
        section(
            "sandbox",
            SandboxConfig,
            dict(
                runtime="docker",
                image=values.get("image", "opencode-cloud/agent_runtime:1.0.0"),
                opencode_internal_port=4096,
                idle_timeout_seconds=1800,
                start_timeout_seconds=60,
                health_interval_seconds=30,
                read_only_rootfs=True,
                tmpfs_mb=256,
                default_cpu=2,
                default_memory_mb=2048,
                default_pids=256,
            ),
        ),
        section(
            "storage",
            StorageConfig,
            dict(
                workspace_root=values.get("workspace_root", "/workspaces"),
                state_root=values.get("state_root", "/state"),
                max_upload_mb=100,
                max_user_workspace_gb=10,
            ),
        ),
        section(
            "opencode",
            OpenCodeConfig,
            dict(
                expected_version="1.18.29",
                health_path="/global/health",
                doc_path="/doc",
                event_path="/event",
                startup_disable_autoupdate=True,
                startup_disable_models_fetch=True,
                startup_disable_default_plugins=True,
                startup_disable_lsp_download=True,
                share_disabled=True,
            ),
        ),
        section(
            "model_gateway",
            ModelGatewayConfig,
            dict(
                base_url=values.get(
                    "model_gateway_public_url", "http://host.docker.internal:8104/v1"
                ),
                health_url=config["services"]["model_gateway"] + "/health/ready",
                routing_strategy="simple-shuffle",
                request_timeout_seconds=120,
            ),
        ),
        section(
            "metrics",
            MetricsConfig,
            dict(
                enabled=True,
                prometheus_path="/metrics",
                prometheus_port=9090,
                grafana_port=3000,
            ),
        ),
        section(
            "performance",
            PerformanceConfig,
            dict(
                controller_overhead_p95_ms=30,
                sandbox_hot_acquire_p95_ms=50,
                sandbox_cold_ready_p95_ms=60000,
                ttft_gateway_overhead_p95_ms=100,
            ),
        ),
        section("load_capacity", LoadCapacityConfig, {}),
    )

    from dataclasses import replace

    return replace(
        result,
        storage=replace(
            result.storage,
            workspace_root=os.environ.get(
                "WORKSPACE_ROOT", result.storage.workspace_root
            ),
            state_root=os.environ.get("STATE_ROOT", result.storage.state_root),
        ),
    )
