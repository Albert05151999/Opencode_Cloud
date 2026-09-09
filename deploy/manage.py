#!/usr/bin/env python3
"""Offline single-host deployment. Uses only Python stdlib and Docker Compose."""
from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse
import urllib.request

BUNDLE = Path(__file__).resolve().parents[1]


def run(args, *, capture=False, env=None):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None, env=env)


def read_config(root):
    cfg = configparser.ConfigParser(interpolation=None)
    if not cfg.read(root / "config.cfg"):
        raise RuntimeError("configuration_missing")
    marker = root / ".instance-id"
    if marker.exists() and marker.read_text().strip() != cfg["platform"]["instance_id"]:
        raise RuntimeError("restore_original_instance_id_before_managing_existing_installation")
    return cfg


def verify_checksums(bundle):
    manifest = bundle / "checksums.sha256"
    if not manifest.is_file():
        raise RuntimeError("checksum_manifest_missing")
    for line in manifest.read_text().splitlines():
        digest, relative = line.split("  ", 1)
        target = (bundle / relative).resolve(strict=True)
        if not target.is_relative_to(bundle.resolve()) or not target.is_file():
            raise RuntimeError("invalid_checksum_path")
        with target.open("rb") as handle:
            if hashlib.file_digest(handle, "sha256").hexdigest() != digest:
                raise RuntimeError("checksum_mismatch")


def copy_new(source, target):
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def load_images(bundle):
    for archive in sorted((bundle / "images").glob("*.tar.zst")):
        decompressor = subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE)
        try:
            result = subprocess.run(["docker", "load"], stdin=decompressor.stdout,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            decompressor.stdout.close()
            if result.returncode or decompressor.wait():
                raise RuntimeError("image_load_failed")
        finally:
            if decompressor.poll() is None:
                decompressor.kill()
                decompressor.wait()


def resolve_images(bundle):
    manifest = json.loads((bundle / "release-images.json").read_text())
    for image in manifest["images"].values():
        original = image["id"]
        for candidate in (original, image["portable_id"]):
            probe = subprocess.run(["docker", "image", "inspect", candidate], capture_output=True, text=True)
            if probe.returncode == 0:
                loaded = json.loads(probe.stdout)[0]
                if loaded["Id"] != candidate:
                    raise RuntimeError("unexpected_loaded_image_identity")
                image.update(source_id=original, id=loaded["Id"])
                break
        else:
            raise RuntimeError("loaded_image_does_not_match_release_digest")
    return manifest


def compose(root, *arguments, capture=False):
    cfg = read_config(root)
    environment = dict(os.environ)
    for name in re.findall(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", (root / ".env").read_text(), re.M):
        environment.pop(name, None)
    return run(["docker", "compose", "--project-name", cfg["platform"]["instance_id"],
                "--env-file", str(root / ".env"), "--file", str(root / "deploy/compose.generated.json"),
                *arguments], capture=capture, env=environment)


def render(root):
    cfg = read_config(root)
    (root / ".instance-id").write_text(cfg["platform"]["instance_id"] + "\n")
    manifest = json.loads((root / "release-images.json").read_text())
    image = lambda name: manifest["images"][name]["id"]
    bridge = json.loads(run(["docker", "network", "inspect", "bridge"], capture=True).stdout)[0]["IPAM"]["Config"][0]["Gateway"]
    gateway_port = urlparse(cfg["model_gateway"]["base_url"]).port or 80
    controller_port = cfg.getint("platform", "port")
    prometheus_port = cfg.getint("metrics", "prometheus_port")
    grafana_port = cfg.getint("metrics", "grafana_port")
    for directory, uid in (("data", 0), ("workspaces", 0), ("state", 0), ("monitoring/prometheus-data", 65534), ("monitoring/grafana-data", 472)):
        p = root / directory
        p.mkdir(parents=True, exist_ok=True)
        os.chown(p, uid, uid)
        if directory.startswith("monitoring/"):
            for base, dirs, files in os.walk(p, followlinks=False):
                for name in dirs + files:
                    os.chown(Path(base) / name, uid, uid, follow_symlinks=False)
    common = {"restart": "unless-stopped", "pull_policy": "never",
              "logging": {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}}}
    services = {}
    services["controller"] = dict(common, image=image("cloud-agent-controller"), network_mode="host", init=True,
        command=["--config", str(root / "config.cfg")], read_only=True, tmpfs=["/tmp:size=128m"], mem_limit="1g",
        volumes=["/var/run/docker.sock:/var/run/docker.sock", f"{root}/config.cfg:{root}/config.cfg:ro",
                 f"{root}/agents:{root}/agents:ro", *[f"{root}/{p}:{root}/{p}" for p in ("data", "workspaces", "state")]])
    variables = [f"{family}_{suffix}" for family in ("CODING_FAST", "CODING_QUALITY", "DATA_FAST", "DATA_QUALITY")
                 for suffix in ("API_KEY", "MODEL", "1_API_BASE", "2_API_BASE")]
    services["model-gateway"] = dict(common, image=image("model-gateway"), mem_limit="2g",
        command=["--config", "/app/config.yaml", "--port", "4000"],
        ports=[f"127.0.0.1:{gateway_port}:4000", f"{bridge}:{gateway_port}:4000"],
        volumes=[f"{root}/config/litellm_config.yaml:/app/config.yaml:ro", f"{root}/deploy/cloud_logging.py:/app/cloud_logging.py:ro"],
        environment={key: "${" + key + ":?configure provider settings}" for key in variables},
        security_opt=["no-new-privileges:true"], cap_drop=["ALL"])
    managed_gateway = root / 'data/management/gateway'
    if (managed_gateway / 'config.json').is_file():
        services['model-gateway']['command'] = ['--config', '/app/managed/config.json', '--port', '4000']
        services['model-gateway']['volumes'].append(f'{managed_gateway}:/app/managed:ro')
    monitoring = root / "monitoring"
    prom_config = {"global": {"scrape_interval": "15s"}, "scrape_configs": [
        {"job_name": "cloud-controller", "metrics_path": cfg["metrics"]["prometheus_path"], "static_configs": [{"targets": [f"127.0.0.1:{controller_port}"]}]},
        {"job_name": "litellm", "metrics_path": "/metrics/", "static_configs": [{"targets": [f"127.0.0.1:{gateway_port}"]}]}]}
    (monitoring / "prometheus.generated.yml").write_text(json.dumps(prom_config))
    (monitoring / "grafana-datasource.generated.yml").write_text(json.dumps({"apiVersion": 1, "datasources": [
        {"name": "Cloud Prometheus", "uid": "cloud-prometheus", "type": "prometheus", "access": "proxy", "url": f"http://127.0.0.1:{prometheus_port}", "isDefault": True}]}))
    password_file = root / ".grafana-admin-password"
    if not password_file.exists():
        password_file.write_text(secrets.token_urlsafe(24))
    password_file.chmod(0o600)
    services["prometheus"] = dict(common, image=image("prometheus"), network_mode="host", mem_limit="512m",
        command=["--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.path=/prometheus", "--storage.tsdb.retention.time=7d", f"--web.listen-address=127.0.0.1:{prometheus_port}"],
        volumes=[f"{monitoring}/prometheus.generated.yml:/etc/prometheus/prometheus.yml:ro", f"{monitoring}/prometheus-data:/prometheus"])
    services["grafana"] = dict(common, image=image("grafana"), network_mode="host", mem_limit="512m",
        environment={"GF_SERVER_HTTP_ADDR": "127.0.0.1", "GF_SERVER_HTTP_PORT": str(grafana_port),
                     "GF_SECURITY_ADMIN_PASSWORD": password_file.read_text().strip(), "GF_ANALYTICS_REPORTING_ENABLED": "false", "GF_ANALYTICS_CHECK_FOR_UPDATES": "false"},
        volumes=[f"{monitoring}/grafana-data:/var/lib/grafana", f"{monitoring}/grafana-datasource.generated.yml:/etc/grafana/provisioning/datasources/cloud.yml:ro",
                 f"{monitoring}/grafana-dashboards.yml:/etc/grafana/provisioning/dashboards/cloud.yml:ro", f"{monitoring}/grafana-dashboard.json:/var/lib/grafana/dashboards/cloud-agent.json:ro"])
    generated = root / "deploy/compose.generated.json"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text(json.dumps({"services": services}, indent=2) + "\n")
    generated.chmod(0o600)


def ready(root, timeout=120):
    cfg = read_config(root)
    urls = [f"http://127.0.0.1:{cfg.getint('platform', 'port')}/cloud/health/ready",
            cfg["model_gateway"]["health_url"],
            f"http://127.0.0.1:{cfg.getint('metrics', 'prometheus_port')}/-/ready",
            f"http://127.0.0.1:{cfg.getint('metrics', 'grafana_port')}/api/health"]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            for url in urls:
                request = urllib.request.Request(url)
                if url == urls[0] and (root / 'data/admin-token').exists():
                    request.add_header('Authorization', 'Bearer ' + (root / 'data/admin-token').read_text().strip())
                with opener.open(request, timeout=2) as response:
                    if response.status != 200:
                        raise RuntimeError("not_ready")
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("service_readiness_timeout")


def stop(root):
    compose(root, "down", "--timeout", "20")
    instance = read_config(root)["platform"]["instance_id"]
    ids = run(["docker", "ps", "-aq", "--filter", f"label=cloud.platform_instance={instance}"], capture=True).stdout.split()
    # Stop/delete only this installation's sandboxes; persistent bind data survives.
    for cid in ids:
        data = json.loads(run(["docker", "inspect", cid], capture=True).stdout)[0]
        if data["Config"]["Labels"].get("cloud.platform_instance") != instance:
            raise RuntimeError("cleanup_ownership_mismatch")
        run(["docker", "stop", "--time", "10", cid], capture=True)
        run(["docker", "rm", cid], capture=True)


def configure_listener(root, host=None, port=None):
    """Preserve existing installations unless explicit listener overrides are supplied."""
    if host is not None and host not in {"127.0.0.1", "0.0.0.0"}:
        raise ValueError("invalid_listener_host")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("invalid_listener_port")
    config = root / "config.cfg"
    exists = config.exists()
    cfg = read_config(root) if exists else configparser.ConfigParser(interpolation=None)
    if not exists:
        if not cfg.read(BUNDLE / "config/config.cfg"):
            raise RuntimeError("bundle_configuration_missing")
        cfg["platform"].update(instance_id="cloud-" + secrets.token_hex(6), data_root=str(root / "data"))
        cfg["storage"].update(workspace_root=str(root / "workspaces"), state_root=str(root / "state"))
    if host is not None:
        cfg["platform"]["host"] = host
    if port is not None:
        cfg["platform"]["port"] = str(port)
    if not exists or host is not None or port is not None:
        if exists:
            shutil.copy2(config, config.with_name(f"config.cfg.before-listener-{time.time_ns()}"))
        with config.open("w") as handle:
            cfg.write(handle)


def install(root, env_file, host=None, port=None):
    if sys.version_info < (3, 11) or not shutil.which("zstd"):
        raise RuntimeError("host_requires_python_3_11_and_zstd")
    old_version = (root / 'VERSION').read_text().strip() if (root / 'VERSION').exists() else None
    new_version = (BUNDLE / 'VERSION').read_text().strip()
    if old_version is not None and old_version != new_version and (old_version, new_version) not in {('0.1.0', '0.2.0'), ('0.1.0', '0.2.1'), ('0.2.0', '0.2.1'), ('0.1.0', '0.2.2'), ('0.2.0', '0.2.2'), ('0.2.1', '0.2.2')}:
        raise RuntimeError("cross_version_upgrade_requires_explicit_migration")
    verify_checksums(BUNDLE)
    root.mkdir(parents=True, exist_ok=True)
    try:
        images = resolve_images(BUNDLE)
    except RuntimeError:
        load_images(BUNDLE)
        images = resolve_images(BUNDLE)
    for subtree in ("deploy", "monitoring", "config", "agents"):
        source = BUNDLE / subtree
        if not source.is_dir():
            continue
        for p in source.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:
                target = root / subtree / p.relative_to(source)
                if subtree == "deploy" and p.suffix in {".py", ".sh"}:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if p.resolve() != target.resolve():
                        shutil.copy2(p, target)
                else:
                    copy_new(p, target)
    for name in ("VERSION", "release-images.json"):
        copy_new(BUNDLE / name, root / name)
    (root / "release-images.json").write_text(json.dumps(images, indent=2) + "\n")
    config = root / "config.cfg"
    configure_listener(root, host, port)
    # The two Docker image stores address identical contents by different digests.
    runtime = images["images"]["cloud-agent-runtime"]
    for path, section in [(config, "sandbox"), *[(p, "agent") for p in (root / "agents").glob("*/agent.cfg")]]:
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read(path)
        if cfg[section]["image"] == runtime["source_id"] and runtime["id"] != runtime["source_id"]:
            shutil.copy2(path, path.with_name(path.name + ".pre-image-store-backup"))
            cfg[section]["image"] = runtime["id"]
            with path.open("w") as handle:
                cfg.write(handle)
    if env_file:
        if not (root / ".env").exists():
            shutil.copyfile(env_file, root / ".env")
            (root / ".env").chmod(0o600)
    if not (root / ".env").is_file():
        raise RuntimeError("provide_env_file_or_install_root_env")
    if new_version in {'0.2.0', '0.2.1', '0.2.2'}:
        prepare_management(root)
    render(root)
    doctor_command = [sys.executable, str(root / "deploy/doctor.py"), "--root", str(root)]
    if compose(root, "ps", "-q", capture=True).stdout.strip():
        doctor_command.append("--allow-running")
    run(doctor_command)
    compose(root, "up", "-d", "--pull", "never")
    ready(root)
    (root / 'VERSION').write_text(new_version + '\n')


def prepare_management(root):
    """Create credentials and an env-referencing baseline without printing secrets."""
    directory = root / 'data/management/gateway'
    directory.mkdir(parents=True, exist_ok=True)
    token = root / 'data/admin-token'
    if not token.exists():
        descriptor = os.open(token, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(secrets.token_urlsafe(48) + '\n')
    token.chmod(0o600)
    if not (directory / 'config.json').exists():
        entries = []
        for name in ('coding-fast', 'coding-quality', 'data-fast', 'data-quality'):
            prefix = name.upper().replace('-', '_')
            for index in (1, 2):
                entries.append({'model_name': name, 'litellm_params': {
                    'model': 'os.environ/' + prefix + '_MODEL', 'api_key': 'os.environ/' + prefix + '_API_KEY',
                    'api_base': 'os.environ/' + prefix + f'_{index}_API_BASE'}, 'model_info': {'id': name + '-' + str(index)}})
        config = {'model_list': entries, 'router_settings': {'routing_strategy': 'least-busy',
            'num_retries': 2, 'timeout': 600, 'allowed_fails': 1, 'cooldown_time': 30},
            'litellm_settings': {'callbacks': ['prometheus', 'cloud_logging.cloud_logger'], 'drop_params': False},
            'general_settings': {'disable_spend_logs': True}}
        path = directory / 'config.json'
        path.write_text(json.dumps(config, indent=2) + '\n')
        path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["install", "start", "stop", "restart", "status", "logs", "uninstall"])
    parser.add_argument("--root", type=Path, default=Path("/srv/cloud-agent"))
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--host", choices=["127.0.0.1", "0.0.0.0"], help="Install: override controller bind address, including existing configuration")
    parser.add_argument("--port", type=int, help="Install: override controller port, including existing configuration")
    args = parser.parse_args()
    if (args.host is not None or args.port is not None) and args.action != "install":
        parser.error("--host and --port are only supported for install")
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    root = args.root.resolve()
    if root == Path("/") or len(root.parts) < 3:
        raise RuntimeError("installation_root_too_broad")
    if args.action not in {"status", "logs"} and os.geteuid() != 0:
        raise RuntimeError("root_required_for_docker_and_user_directories")
    if args.action == "install":
        install(root, args.env_file, args.host, args.port)
    elif args.action in {"stop", "uninstall"}:
        stop(root)
    elif args.action in {"start", "restart"}:
        if args.action == "restart":
            stop(root)
        render(root)
        run([sys.executable, str(root / "deploy/doctor.py"), "--root", str(root), "--allow-running"])
        compose(root, "up", "-d", "--pull", "never")
        ready(root)
    elif args.action == "status":
        compose(root, "ps", "--format", "json")
        ready(root, timeout=5)
    else:
        compose(root, "logs", "--tail", "100")
    print(json.dumps({"result": "passed", "action": args.action, "root": str(root), "persistent_data_retained": True}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"result": "failed", "error": type(exc).__name__,
                          "reason": str(exc) if isinstance(exc, RuntimeError) else "operation_failed"}), file=sys.stderr)
        raise SystemExit(1)
