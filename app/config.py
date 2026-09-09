"""Typed INI configuration with strict environment overrides."""
from __future__ import annotations

import configparser
from dataclasses import asdict, dataclass
import os
from pathlib import Path, PurePosixPath
from typing import Mapping
from urllib.parse import urlparse


ENV_PREFIX = "CLOUD_AGENT__"
REQUIRED_SECTIONS = (
    "platform", "auth", "sandbox", "storage", "opencode",
    "model_gateway", "metrics", "performance",
)


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class PlatformConfig:
    instance_id: str
    host: str
    port: int
    log_level: str
    data_root: str
    sqlite_synchronous: str = "FULL"


@dataclass(frozen=True)
class AuthConfig:
    enabled: bool
    jwt_header: str
    jwt_algorithm: str
    jwt_issuer: str
    cookie_token_endpoint: str
    token_endpoint_enabled: bool = True


@dataclass(frozen=True)
class SandboxConfig:
    runtime: str
    image: str
    opencode_internal_port: int
    idle_timeout_seconds: int
    start_timeout_seconds: int
    health_interval_seconds: int
    read_only_rootfs: bool
    tmpfs_mb: int
    default_cpu: float
    default_memory_mb: int
    default_pids: int
    health_failure_threshold: int = 3


@dataclass(frozen=True)
class StorageConfig:
    workspace_root: str
    state_root: str
    max_upload_mb: int
    max_user_workspace_gb: int


@dataclass(frozen=True)
class OpenCodeConfig:
    expected_version: str
    health_path: str
    doc_path: str
    event_path: str
    startup_disable_autoupdate: bool
    startup_disable_models_fetch: bool
    startup_disable_default_plugins: bool
    startup_disable_lsp_download: bool
    share_disabled: bool


@dataclass(frozen=True)
class ModelGatewayConfig:
    base_url: str
    health_url: str
    routing_strategy: str
    request_timeout_seconds: int


@dataclass(frozen=True)
class MetricsConfig:
    enabled: bool
    prometheus_path: str
    prometheus_port: int
    grafana_port: int


@dataclass(frozen=True)
class PerformanceConfig:
    controller_overhead_p95_ms: int
    sandbox_hot_acquire_p95_ms: int
    sandbox_cold_ready_p95_ms: int
    ttft_gateway_overhead_p95_ms: int


@dataclass(frozen=True)
class AppConfig:
    platform: PlatformConfig
    auth: AuthConfig
    sandbox: SandboxConfig
    storage: StorageConfig
    opencode: OpenCodeConfig
    model_gateway: ModelGatewayConfig
    metrics: MetricsConfig
    performance: PerformanceConfig

    def safe_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _apply_environment(parser: configparser.ConfigParser, environ: Mapping[str, str]) -> None:
    for name, value in environ.items():
        if not name.startswith(ENV_PREFIX):
            continue
        parts = name[len(ENV_PREFIX):].lower().split("__")
        if len(parts) != 2 or not all(parts):
            raise ConfigurationError(f"Invalid environment override name: {name}")
        section, key = parts
        if not parser.has_section(section) or not parser.has_option(section, key):
            raise ConfigurationError(f"Unknown environment override: {name}")
        parser.set(section, key, value)


def _reject_secrets(parser: configparser.ConfigParser) -> None:
    forbidden = ("secret", "password", "api_key", "access_token", "private_key")
    for section in parser.sections():
        for key in parser[section]:
            lowered = key.lower()
            if any(lowered == item or lowered.endswith(f"_{item}") for item in forbidden):
                raise ConfigurationError(f"Secret setting [{section}] {key} must use the environment")


def _positive(value: int | float, label: str) -> int | float:
    if value <= 0:
        raise ConfigurationError(f"{label} must be greater than zero")
    return value


def _port(value: int, label: str) -> int:
    if not 1 <= value <= 65535:
        raise ConfigurationError(f"{label} must be between 1 and 65535")
    return value


def _absolute_linux_path(value: str, label: str) -> str:
    path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ConfigurationError(f"{label} must be an absolute normalized Linux path")
    return str(path)


def _api_path(value: str, label: str) -> str:
    if not value.startswith("/") or value.startswith("//"):
        raise ConfigurationError(f"{label} must start with one slash")
    return value


def _http_url(value: str, label: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigurationError(f"{label} must be an HTTP(S) URL")
    return value


def load_config(path: str | Path = "config.cfg", environ: Mapping[str, str] | None = None) -> AppConfig:
    parser = configparser.ConfigParser(interpolation=None)
    loaded = parser.read(Path(path), encoding="utf-8")
    if not loaded:
        raise ConfigurationError(f"Configuration file not found: {path}")
    missing = [section for section in REQUIRED_SECTIONS if not parser.has_section(section)]
    if missing:
        raise ConfigurationError(f"Missing configuration sections: {', '.join(missing)}")
    _reject_secrets(parser)
    _apply_environment(parser, os.environ if environ is None else environ)
    try:
        platform = PlatformConfig(
            instance_id=parser.get("platform", "instance_id"),
            host=parser.get("platform", "host"),
            port=_port(parser.getint("platform", "port"), "platform.port"),
            log_level=parser.get("platform", "log_level").upper(),
            data_root=_absolute_linux_path(parser.get("platform", "data_root"), "platform.data_root"),
            sqlite_synchronous=parser.get("platform", "sqlite_synchronous", fallback="FULL").upper(),
        )
        if platform.sqlite_synchronous not in {"NORMAL", "FULL"}:
            raise ConfigurationError("platform.sqlite_synchronous must be NORMAL or FULL")
        auth = AuthConfig(
            enabled=parser.getboolean("auth", "enabled"),
            jwt_header=parser.get("auth", "jwt_header"),
            jwt_algorithm=parser.get("auth", "jwt_algorithm"),
            jwt_issuer=parser.get("auth", "jwt_issuer"),
            cookie_token_endpoint=_api_path(parser.get("auth", "cookie_token_endpoint"), "auth.cookie_token_endpoint"),
            token_endpoint_enabled=parser.getboolean("auth", "token_endpoint_enabled", fallback=True),
        )
        if not auth.cookie_token_endpoint.startswith("/cloud/auth/"):
            raise ConfigurationError("auth.cookie_token_endpoint must remain under /cloud/auth/")
        sandbox = SandboxConfig(
            runtime=parser.get("sandbox", "runtime"), image=parser.get("sandbox", "image"),
            opencode_internal_port=_port(parser.getint("sandbox", "opencode_internal_port"), "sandbox.opencode_internal_port"),
            idle_timeout_seconds=int(_positive(parser.getint("sandbox", "idle_timeout_seconds"), "sandbox.idle_timeout_seconds")),
            start_timeout_seconds=int(_positive(parser.getint("sandbox", "start_timeout_seconds"), "sandbox.start_timeout_seconds")),
            health_interval_seconds=int(_positive(parser.getint("sandbox", "health_interval_seconds"), "sandbox.health_interval_seconds")),
            read_only_rootfs=parser.getboolean("sandbox", "read_only_rootfs"),
            tmpfs_mb=int(_positive(parser.getint("sandbox", "tmpfs_mb"), "sandbox.tmpfs_mb")),
            default_cpu=float(_positive(parser.getfloat("sandbox", "default_cpu"), "sandbox.default_cpu")),
            default_memory_mb=int(_positive(parser.getint("sandbox", "default_memory_mb"), "sandbox.default_memory_mb")),
            default_pids=int(_positive(parser.getint("sandbox", "default_pids"), "sandbox.default_pids")),
            health_failure_threshold=int(_positive(parser.getint("sandbox", "health_failure_threshold", fallback=3), "sandbox.health_failure_threshold")),
        )
        storage = StorageConfig(
            workspace_root=_absolute_linux_path(parser.get("storage", "workspace_root"), "storage.workspace_root"),
            state_root=_absolute_linux_path(parser.get("storage", "state_root"), "storage.state_root"),
            max_upload_mb=int(_positive(parser.getint("storage", "max_upload_mb"), "storage.max_upload_mb")),
            max_user_workspace_gb=int(_positive(parser.getint("storage", "max_user_workspace_gb"), "storage.max_user_workspace_gb")),
        )
        opencode = OpenCodeConfig(
            expected_version=parser.get("opencode", "expected_version"),
            health_path=_api_path(parser.get("opencode", "health_path"), "opencode.health_path"),
            doc_path=_api_path(parser.get("opencode", "doc_path"), "opencode.doc_path"),
            event_path=_api_path(parser.get("opencode", "event_path"), "opencode.event_path"),
            startup_disable_autoupdate=parser.getboolean("opencode", "startup_disable_autoupdate"),
            startup_disable_models_fetch=parser.getboolean("opencode", "startup_disable_models_fetch"),
            startup_disable_default_plugins=parser.getboolean("opencode", "startup_disable_default_plugins"),
            startup_disable_lsp_download=parser.getboolean("opencode", "startup_disable_lsp_download"),
            share_disabled=parser.getboolean("opencode", "share_disabled"),
        )
        model_gateway = ModelGatewayConfig(
            base_url=_http_url(parser.get("model_gateway", "base_url"), "model_gateway.base_url"),
            health_url=_http_url(parser.get("model_gateway", "health_url"), "model_gateway.health_url"),
            routing_strategy=parser.get("model_gateway", "routing_strategy"),
            request_timeout_seconds=int(_positive(parser.getint("model_gateway", "request_timeout_seconds"), "model_gateway.request_timeout_seconds")),
        )
        metrics = MetricsConfig(
            enabled=parser.getboolean("metrics", "enabled"),
            prometheus_path=_api_path(parser.get("metrics", "prometheus_path"), "metrics.prometheus_path"),
            prometheus_port=_port(parser.getint("metrics", "prometheus_port"), "metrics.prometheus_port"),
            grafana_port=_port(parser.getint("metrics", "grafana_port"), "metrics.grafana_port"),
        )
        performance = PerformanceConfig(**{
            key: int(_positive(parser.getint("performance", key), f"performance.{key}"))
            for key in PerformanceConfig.__dataclass_fields__
        })
    except (configparser.Error, ValueError) as exc:
        if isinstance(exc, ConfigurationError):
            raise
        raise ConfigurationError(str(exc)) from exc
    if sandbox.runtime != "runc":
        raise ConfigurationError("sandbox.runtime must be runc for V1")
    if not all((opencode.startup_disable_autoupdate, opencode.startup_disable_models_fetch,
                opencode.startup_disable_default_plugins, opencode.startup_disable_lsp_download,
                opencode.share_disabled)):
        raise ConfigurationError("OpenCode safety and deterministic-start flags must stay enabled")
    return AppConfig(platform, auth, sandbox, storage, opencode, model_gateway, metrics, performance)
