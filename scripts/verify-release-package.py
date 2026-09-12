#!/usr/bin/env python3
"""Verify a release ZIP inside a fresh, isolated Docker-in-Docker daemon."""
from __future__ import annotations

import argparse
import io
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import docker


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts" / "release" / "package-verification.json"
LABEL = "cloud.release_package_verification"


class VerificationError(RuntimeError):
    pass


def read_version_value(name: str, path: Path = ROOT / "versions.env") -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key == name and value:
            return value
    raise VerificationError("acceptance_image_missing")


def validate_zip(path: Path) -> str:
    if not path.is_file():
        raise VerificationError("zip_missing")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        roots = set()
        if not members:
            raise VerificationError("zip_empty")
        for member in members:
            if "\\" in member.filename or "\x00" in member.filename:
                raise VerificationError("zip_path_unsafe")
            item = PurePosixPath(member.filename)
            if item.is_absolute() or ".." in item.parts or not item.parts:
                raise VerificationError("zip_path_unsafe")
            roots.add(item.parts[0])
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise VerificationError("zip_symlink_unsupported")
        if len(roots) != 1 or not next(iter(roots)).startswith("cloud-agent-release-"):
            raise VerificationError("zip_root_invalid")
        return next(iter(roots))


def env_archive(content: bytes) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        info = tarfile.TarInfo("provider.env")
        info.size = len(content)
        info.mode = 0o600
        info.uid = info.gid = 0
        archive.addfile(info, io.BytesIO(content))
    return stream.getvalue()


def step(container, report: dict, name: str, command: list[str]) -> bytes:
    result = container.exec_run(command, demux=False)
    code = int(result.exit_code)
    report["steps"].append({"name": name, "exit_code": code})
    if name == 'doctor_precheck':
        try:
            observed = json.loads(result.output)
            report['preflight'] = {k: observed[k] for k in ('result', 'checks', 'errors', 'profile', 'policy') if k in observed}
        except (ValueError, TypeError):
            pass
    if code:
        raise VerificationError(name + "_failed")
    return result.output or b""


def wait_engine(container, report: dict, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = container.exec_run(["docker", "info", "--format", "{{json .ServerVersion}}"])
        if result.exit_code == 0:
            report["steps"].append({"name": "docker_ready", "exit_code": 0})
            return
        time.sleep(1)
    raise VerificationError("inner_docker_not_ready")


def swap_current(container) -> int | None:
    code = '''from pathlib import Path
rows = [line.split(":", 2) for line in Path("/proc/self/cgroup").read_text().splitlines()]
for _, controllers, relative in rows:
    if not controllers:
        for base in (Path("/sys/fs/cgroup") / relative.lstrip("/"), Path("/sys/fs/cgroup")):
            path = base / "memory.swap.current"
            if path.is_file():
                print(int(path.read_text())); raise SystemExit
for _, controllers, relative in rows:
    if "memory" in controllers.split(","):
        for base in (Path("/sys/fs/cgroup/memory") / relative.lstrip("/"), Path("/sys/fs/cgroup/memory")):
            path = base / "memory.stat"
            if path.is_file():
                values = dict(line.split() for line in path.read_text().splitlines())
                if "total_swap" in values:
                    print(int(values["total_swap"])); raise SystemExit
'''
    command = ["python3", "-c", code]
    result = container.exec_run(command)
    try:
        return int((result.output or b"").strip()) if result.exit_code == 0 and result.output.strip() else None
    except ValueError:
        return None


def verify(zip_path: Path, env_path: Path, profile: str = 'strict') -> dict:
    package_root = validate_zip(zip_path)
    if not env_path.is_file():
        raise VerificationError("env_file_missing")
    secret_content = env_path.read_bytes()
    fixture = uuid.uuid4().hex
    name = "cloud-package-" + fixture[:12]
    report = {
        "result": "running", "fixture": fixture, "outer_image": read_version_value("ACCEPTANCE_DIND_IMAGE"), "profile": profile,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "initial_images_empty": False, "no_development_checkout_mount": True, "steps": [], "image_ids": {},
        "resources": {"memory_bytes": 10 * 1024**3, "swap_limit_bytes": 0, "nano_cpus": 8_000_000_000},
    }
    with zip_path.open("rb") as handle:
        report["zip_sha256"] = hashlib.file_digest(handle, "sha256").hexdigest()
    client = docker.from_env()
    container = None
    docker_root = Path(tempfile.mkdtemp(prefix="cloud-package-docker-", dir="/tmp"))
    cleanup_errors = []
    try:
        container = client.containers.run(
            report["outer_image"], detach=True, name=name, privileged=True,
            labels={LABEL: fixture}, environment={"DOCKER_TLS_CERTDIR": ""},
            volumes={str(docker_root): {"bind": "/var/lib/docker", "mode": "rw"}},
            # Equal memory and memory-swap limits prohibit swap for this fixture.
            mem_limit="10g", memswap_limit="10g", nano_cpus=8_000_000_000,
            command=["--bip=172.30.0.1/16", "--default-address-pool=base=172.31.0.0/16,size=24", "--storage-driver=overlay2"],
        )
        wait_engine(container, report)
        initial = step(container, report, "initial_image_inventory", ["docker", "image", "ls", "-q"])
        report["initial_images_empty"] = not initial.strip()
        if not report["initial_images_empty"]:
            raise VerificationError("initial_images_not_empty")
        step(container, report, "install_host_prerequisites", ["apk", "add", "--no-cache", "bash", "python3", "zstd", "unzip"])
        copied = subprocess.run(
            ["docker", "cp", str(zip_path.resolve()), f"{name}:/root/release.zip"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        report["steps"].append({"name": "copy_zip", "exit_code": copied.returncode})
        if copied.returncode:
            raise VerificationError("copy_zip_failed")
        if not container.put_archive("/root", env_archive(secret_content)):
            raise VerificationError("env_archive_failed")
        report["steps"].append({"name": "inject_env_archive", "exit_code": 0})
        release = f"/release/{package_root}"
        step(container, report, "unzip", ["unzip", "-q", "/root/release.zip", "-d", "/release"])
        if profile == 'coexistence-trial':
            step(container, report, 'select_trial_profile', ['python3', '-c',
                'from pathlib import Path; p=Path("/srv/cloud-agent"); p.mkdir(parents=True,exist_ok=True); '
                '(p/".preflight-profile").write_text("coexistence-trial\\n")'])
        step(container, report, "doctor_precheck", ["python3", f"{release}/deploy/doctor.py", "--root", "/srv/cloud-agent", "--config", f"{release}/config/config.cfg", "--skip-image-check"])
        step(container, report, "install", ["bash", f"{release}/deploy/install.sh", "--root", "/srv/cloud-agent", "--env-file", "/root/provider.env"])
        manifest = json.loads(step(container, report, "read_release_manifest", ["cat", "/srv/cloud-agent/release-images.json"]))
        for image_name, metadata in manifest["images"].items():
            image_id = metadata["id"]
            observed = step(container, report, "inspect_" + image_name, ["docker", "image", "inspect", "--format", "{{.Id}}", image_id]).decode().strip()
            if observed != image_id:
                raise VerificationError("image_identity_mismatch")
            report["image_ids"][image_name] = image_id
        try:
            step(container, report, "smoke", ["python3", "/srv/cloud-agent/deploy/smoke.py", "--burst", "--output", "/root/smoke.json"])
        except VerificationError:
            pass  # Preserve the safe failure report before rejecting the gate.
        smoke = json.loads(step(container, report, "read_smoke_result", ["cat", "/root/smoke.json"]))
        report["smoke"] = smoke
        if smoke.get("result") != "passed":
            raise VerificationError("smoke_result_failed")
        marker = smoke["ordinary"]["files"]["path"]
        username = smoke["ordinary"]["users"]["agent-code"]
        marker_path = f"/srv/cloud-agent/workspaces/agent-code/{username}/shared/{marker}"
        step(container, report, "restart", ["bash", "/srv/cloud-agent/deploy/restart.sh", "--root", "/srv/cloud-agent"])
        step(container, report, "status", ["bash", "/srv/cloud-agent/deploy/status.sh", "--root", "/srv/cloud-agent"])
        step(container, report, "marker_after_restart", ["test", "-f", marker_path])
        step(container, report, "uninstall", ["bash", "/srv/cloud-agent/deploy/uninstall.sh", "--root", "/srv/cloud-agent"])
        remaining = step(container, report, "inner_containers_empty", ["docker", "ps", "-aq"])
        if remaining.strip():
            raise VerificationError("inner_containers_remain")
        for check_name, path in (("marker_retained", marker_path), ("config_retained", "/srv/cloud-agent/config.cfg"), ("env_retained", "/srv/cloud-agent/.env")):
            step(container, report, check_name, ["test", "-f", path])
        report["resources"]["swap_current_bytes"] = swap_current(container)
        container.reload()
        report["resources"]["oom_killed"] = bool(container.attrs.get("State", {}).get("OOMKilled"))
        if report["resources"]["oom_killed"]:
            raise VerificationError("outer_oom_killed")
        if report["resources"]["swap_current_bytes"] != 0:
            raise VerificationError("swap_detected")
        report["result"] = "passed"
    except VerificationError as exc:
        report.update(result="failed", error_category=str(exc))
    except Exception:
        report.update(result="failed", error_category="verification_operation_failed")
    finally:
        secret_content = b""
        try:
            owned = client.containers.list(all=True, filters={"label": f"{LABEL}={fixture}"})
            for owned_container in owned:
                owned_container.remove(force=True)
        except Exception:
            cleanup_errors.append("outer_container_cleanup_failed")
        try:
            resolved = docker_root.resolve()
            if resolved.parent != Path("/tmp") or not resolved.name.startswith("cloud-package-docker-"):
                raise VerificationError("invalid_cleanup_root")
            shutil.rmtree(resolved)
        except Exception:
            cleanup_errors.append("docker_root_cleanup_failed")
        try:
            client.close()
        except Exception:
            cleanup_errors.append("docker_client_cleanup_failed")
        if cleanup_errors:
            report.update(result="failed", cleanup_errors=cleanup_errors)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip", type=Path)
    parser.add_argument("--env-file", type=Path, default=ROOT / "deploy" / ".env")
    parser.add_argument('--profile', choices=['strict', 'coexistence-trial'], default='strict')
    args = parser.parse_args()
    try:
        report = verify(args.zip.resolve(), args.env_file.resolve(), args.profile)
    except VerificationError as exc:
        report = {"result": "failed", "error_category": str(exc), "steps": []}
    except Exception:
        report = {"result": "failed", "error_category": "verification_setup_failed", "steps": []}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if report.get("fixture"):
        (REPORT.parent / ("package-" + report["fixture"] + ".json")).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"result": report["result"], "report": str(REPORT)}))
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
