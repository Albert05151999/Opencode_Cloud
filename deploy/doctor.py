#!/usr/bin/env python3
"""Preflight a release host without importing controller dependencies."""
from __future__ import annotations

import argparse
import configparser
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse


MIN_ENGINE = (29, 8, 0)
MIN_TOTAL_KIB = 8 * 1024 * 1024
MIN_AVAILABLE_KIB = 3 * 1024 * 1024
MIN_DISK_BYTES = 8 * 1024**3


def host_policy(engine: str, memory: dict[str, int], profile: str) -> dict:
    if profile not in {"strict", "coexistence-trial"}:
        raise ValueError("unknown preflight profile")
    trial = profile == "coexistence-trial"
    minimum_engine = (29, 7, 2) if trial else MIN_ENGINE
    minimum_total = 7 * 1024 * 1024 if trial else MIN_TOTAL_KIB
    swap_used = max(0, memory["SwapTotal"] - memory["SwapFree"])
    return {
        "docker_engine": version_tuple(engine) >= minimum_engine,
        "memory": memory["MemTotal"] >= minimum_total and memory["MemAvailable"] >= MIN_AVAILABLE_KIB
                  and (trial or swap_used == 0),
        "observed_memory_kib": memory,
        "swap_used_kib": swap_used,
        "warnings": (["Trial admission only; Docker compatibility and load acceptance are not established.",
                      "Use one active sandbox/request initially; concurrency is not automatically limited.",
                      "Existing swap occupancy is allowed; monitor vmstat si/so during trial."] if trial else []),
    }


def version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for part in value.split("."):
        digits = "".join(char for char in part if char.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def read_meminfo(path: Path = Path("/proc/meminfo")) -> dict[str, int]:
    result = {}
    for line in path.read_text(encoding="ascii").splitlines():
        name, value = line.split(":", 1)
        result[name] = int(value.strip().split()[0])
    return result


def read_release_image(root: Path) -> str:
    manifest = json.loads((root / "release-images.json").read_text(encoding="utf-8"))
    image_id = manifest["images"]["cloud-agent-controller"]["id"]
    if not isinstance(image_id, str) or not image_id.startswith("sha256:"):
        raise ValueError("invalid controller image id")
    return image_id


def parse_layout(config_path: Path, root: Path) -> tuple[list[int], list[str]]:
    parser = configparser.ConfigParser(interpolation=None)
    if parser.read(config_path, encoding="utf-8") != [str(config_path)]:
        raise ValueError("config unavailable")
    required = {"platform", "storage", "model_gateway", "metrics"}
    if not required.issubset(parser.sections()):
        raise ValueError("config sections missing")
    data_root = Path(parser.get("platform", "data_root"))
    workspace = Path(parser.get("storage", "workspace_root"))
    state = Path(parser.get("storage", "state_root"))
    expected = (root / "data", root / "workspaces", root / "state")
    if not all(path.is_absolute() for path in (data_root, workspace, state)):
        raise ValueError("layout path is not absolute")
    if (data_root, workspace, state) != expected:
        raise ValueError("layout path does not match release root")

    host = parser.get("platform", "host")
    gateway = urlparse(parser.get("model_gateway", "base_url"))
    if host not in {"127.0.0.1", "0.0.0.0"}:
        raise ValueError("controller host must be 127.0.0.1 or 0.0.0.0")
    if gateway.hostname != "127.0.0.1" or gateway.port is None:
        raise ValueError("model gateway must remain bound to loopback")
    ports = [
        parser.getint("platform", "port"), parser.getint("metrics", "prometheus_port"),
        parser.getint("metrics", "grafana_port"), gateway.port,
    ]
    if len(set(ports)) != len(ports) or any(port < 1 or port > 65535 for port in ports):
        raise ValueError("invalid or duplicate service port")
    return ports, [str(path) for path in (data_root, workspace, state)]


def write_probe(paths: list[str]) -> None:
    for value in paths:
        directory = Path(value)
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, probe = tempfile.mkstemp(prefix=".doctor-", dir=directory)
        os.close(descriptor)
        Path(probe).unlink()


def ports_idle(ports: list[int]) -> bool:
    listeners = []
    try:
        for port in ports:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listeners.append(listener)
            # A stopped HTTP server can leave TIME_WAIT sockets behind. Match
            # normal server reuse semantics, then listen to detect a live owner.
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("0.0.0.0", port))
            listener.listen(1)
        return True
    except OSError:
        return False
    finally:
        for listener in listeners:
            listener.close()


def run_json(command: list[str]) -> dict:
    completed = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(completed.stdout)


def validate_config_in_image(image_id: str, config_path: Path) -> None:
    subprocess.run([
        "docker", "run", "--rm", "--network", "none", "--mount",
        f"type=bind,src={config_path.resolve()},dst=/doctor/config.cfg,readonly",
        "--entrypoint", "python", image_id, "-m", "app.main", "--check-config",
        "--config", "/doctor/config.cfg",
    ], check=True, capture_output=True, text=True, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/srv/cloud-agent"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--allow-running", action="store_true")
    parser.add_argument("--skip-image-check", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    config_path = (args.config or root / "config.cfg").resolve()
    profile_file = root / ".preflight-profile"
    profile = profile_file.read_text().strip() if profile_file.exists() else "strict"
    if profile not in {"strict", "coexistence-trial"}:
        print(json.dumps({"result": "failed", "errors": ["invalid_preflight_profile"]}))
        return 1
    checks: dict[str, bool] = {}
    errors: set[str] = set()
    system = {"os": platform.system(), "kernel": platform.release(), "machine": platform.machine()}

    def check(category: str, operation) -> None:
        try:
            checks[category] = bool(operation())
        except (OSError, ValueError, KeyError, configparser.Error, subprocess.SubprocessError, json.JSONDecodeError):
            checks[category] = False
        if not checks[category]:
            errors.add(category)

    check("platform", lambda: platform.system() == "Linux" and platform.machine().lower() in {"x86_64", "amd64"})
    check("docker_cli", lambda: shutil.which("docker") is not None)
    check("docker_compose", lambda: subprocess.run(["docker", "compose", "version"], capture_output=True).returncode == 0)
    docker_info: dict = {}
    try:
        docker_info = run_json(["docker", "info", "--format", "{{json .}}"])
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        errors.add("docker_engine")
        checks["docker_engine"] = False
    else:
        runtimes = docker_info.get("Runtimes") or {}
        checks["docker_engine"] = version_tuple(str(docker_info.get("ServerVersion", ""))) >= MIN_ENGINE
        checks["runc"] = docker_info.get("DefaultRuntime") == "runc" and "runc" in runtimes
        checks["resource_controls"] = bool(docker_info.get("MemoryLimit")) and bool(docker_info.get("PidsLimit")) and str(docker_info.get("CgroupVersion")) in {"1", "2"}
        errors.update(name for name in ("docker_engine", "runc", "resource_controls") if not checks[name])
        system.update({
            "docker_engine": str(docker_info.get("ServerVersion", "unknown")),
            "default_runtime": str(docker_info.get("DefaultRuntime", "unknown")),
            "cgroup_version": str(docker_info.get("CgroupVersion", "unknown")),
        })

    policy = {}
    try:
        policy = host_policy(str(docker_info.get("ServerVersion", "")), read_meminfo(), profile)
        checks["docker_engine"] = policy["docker_engine"]
        checks["memory"] = policy["memory"]
        for name in ("docker_engine", "memory"):
            if checks[name]:
                errors.discard(name)
            else:
                errors.add(name)
    except (OSError, ValueError, KeyError):
        checks["memory"] = False
        errors.add("memory")
    check("disk", lambda: shutil.disk_usage(root if root.exists() else root.parent).free >= MIN_DISK_BYTES)
    layout_paths: list[str] = []
    ports: list[int] = []
    try:
        ports, layout_paths = parse_layout(config_path, root)
        write_probe(layout_paths)
        checks["layout"] = True
    except (OSError, ValueError, configparser.Error):
        checks["layout"] = False
        errors.add("layout")
    checks["ports_idle"] = args.allow_running or (bool(ports) and ports_idle(ports))
    if not checks["ports_idle"]:
        errors.add("ports_idle")

    image_validation = "skipped_unverified" if args.skip_image_check else "required"
    if args.skip_image_check:
        checks["config"] = False
    else:
        try:
            controller_image = read_release_image(root)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            checks["config"] = False
            errors.add("release_images_missing")
            image_validation = "failed"
        else:
            try:
                subprocess.run(["docker", "image", "inspect", controller_image], check=True, capture_output=True)
            except (OSError, subprocess.SubprocessError):
                checks["config"] = False
                errors.add("controller_image_unavailable")
                image_validation = "failed"
            else:
                try:
                    validate_config_in_image(controller_image, config_path)
                    checks["config"] = True
                    image_validation = "passed"
                except (OSError, subprocess.SubprocessError):
                    checks["config"] = False
                    errors.add("config_image_validation")
                    image_validation = "failed"

    report = {"result": "failed" if errors else "passed", "system": system, "checks": checks, "image_validation": image_validation}
    report.update(profile=profile, policy=policy)
    if errors:
        report["errors"] = sorted(errors)
    print(json.dumps(report, separators=(",", ":")))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
