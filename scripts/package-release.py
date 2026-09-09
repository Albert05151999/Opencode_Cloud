#!/usr/bin/env python3
"""Stage an allowlisted offline bundle, or ZIP an already verified stage."""
import argparse
import configparser
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def copy(source, target):
    if source.is_symlink():
        raise RuntimeError("symlink_in_release_input")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def checksums(directory):
    lines = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name != "checksums.sha256":
            with path.open("rb") as handle:
                lines.append(hashlib.file_digest(handle, "sha256").hexdigest() + "  " + path.relative_to(directory).as_posix())
    (directory / "checksums.sha256").write_text("\n".join(lines) + "\n")


def export_image(reference, archive):
    if archive.exists():
        return
    partial = archive.with_suffix(archive.suffix + ".partial")
    save = subprocess.Popen(["docker", "save", reference], stdout=subprocess.PIPE)
    try:
        compression = subprocess.run(["zstd", "-T2", "-6", "-q", "-f", "-o", str(partial)], stdin=save.stdout)
        save.stdout.close()
        if compression.returncode or save.wait():
            raise RuntimeError("image_export_failed")
        partial.replace(archive)
    finally:
        if save.poll() is None:
            save.kill()
            save.wait()
        partial.unlink(missing_ok=True)


def portable_identity(archive):
    process = subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE)
    config = None
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as stream:
            for member in stream:
                if member.name == "manifest.json":
                    manifests = json.load(stream.extractfile(member))
                    if len(manifests) != 1:
                        raise RuntimeError("expected_single_image_archive")
                    config = manifests[0]["Config"]
        if process.wait():
            raise RuntimeError("archive_read_failed")
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.kill()
            process.wait()
    if config is None:
        raise RuntimeError("docker_archive_manifest_missing")
    digest = Path(config).name.removesuffix(".json")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise RuntimeError("invalid_image_config_digest")
    return "sha256:" + digest


def stage(directory):
    build = json.loads((ROOT / "artifacts/release/image-build.json").read_text())
    if build["version"] != (ROOT / "VERSION").read_text().strip():
        raise RuntimeError("image_build_version_mismatch_rebuild_images")
    if build["result"] != "passed":
        raise RuntimeError("image_build_gate_not_passed")
    versions = dict(line.split("=", 1) for line in (ROOT / "versions.env").read_text().splitlines() if "=" in line)
    images = dict(build["images"])
    for name in ("prometheus", "grafana"):
        reference = versions[name.upper() + "_IMAGE"]
        item = json.loads(subprocess.check_output(["docker", "image", "inspect", reference]))[0]
        images[name] = {"tag": reference, "id": item["Id"], "size": item["Size"]}
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "images").mkdir(exist_ok=True)
    for name, metadata in images.items():
        actual = json.loads(subprocess.check_output(["docker", "image", "inspect", metadata["tag"]]))[0]
        if actual["Id"] != metadata["id"]:
            raise RuntimeError("image_tag_changed_since_verification")
        # Digest in filename prevents cache reuse after a rebuild under the same release tag.
        filename = f"{name}_{build['version']}_{metadata['id'][7:19]}.tar.zst"
        metadata = dict(metadata, archive="images/" + filename)
        images[name] = metadata
        export_image(metadata["tag"], directory / metadata["archive"])
        metadata["portable_id"] = portable_identity(directory / metadata["archive"])
    expected_archives = {item["archive"] for item in images.values()}
    for old in (directory / "images").glob("*.tar.zst"):
        if old.relative_to(directory).as_posix() not in expected_archives:
            raise RuntimeError("stale_image_archive_in_stage_use_new_directory")
    for name in ("VERSION", "versions.env", "01_architecture.md", "02_api_contract.md"):
        copy(ROOT / name, directory / name)
    copy(ROOT / "docs/release-readme.md", directory / "README.md")
    copy(ROOT / "docs/upstream/opencode-1.18.29-openapi.json", directory / "docs/upstream/opencode-1.18.29-openapi.json")
    for folder in ("agents", "monitoring"):
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                copy(path, directory / path.relative_to(ROOT))
    for name in ("manage.py", "doctor.py", "smoke.py", "cloud_logging.py", "doctor.sh", "install.sh", "start.sh", "stop.sh", "restart.sh", "status.sh", "logs.sh", "uninstall.sh", ".env.example"):
        copy(ROOT / "deploy" / name, directory / "deploy" / name)
    copy(ROOT / "config/litellm_config.yaml", directory / "config/litellm_config.yaml")
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(ROOT / "config.cfg")
    cfg["platform"].update(host="0.0.0.0", port="18080", data_root="/srv/cloud-agent/data")
    cfg["sandbox"]["image"] = images["cloud-agent-runtime"]["id"]
    with (directory / "config/config.cfg").open("w") as handle:
        cfg.write(handle)
    for agent_cfg in (directory / "agents").glob("*/agent.cfg"):
        agent = configparser.ConfigParser(interpolation=None)
        agent.read(agent_cfg)
        agent["agent"]["image"] = images["cloud-agent-runtime"]["id"]
        with agent_cfg.open("w") as handle:
            agent.write(handle)
    (directory / "release-images.json").write_text(json.dumps({"version": build["version"], "images": images}, indent=2) + "\n")
    for path in directory.rglob("*"):
        if path.is_file() and (path.name == ".env" or path.suffix == ".pyc" or path.is_symlink()):
            raise RuntimeError("forbidden_release_file")
    spec = importlib.util.spec_from_file_location("release_image_audit", ROOT / "scripts/audit-release-images.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    secret_values = [value.encode() for value in audit.parse_env_file(ROOT / "deploy/.env")]
    for path in directory.rglob("*"):
        if path.is_file() and path.relative_to(directory).parts[0] != "images":
            content = path.read_bytes()
            if any(value in content for value in secret_values):
                raise RuntimeError("provider_secret_in_release_file")
    checksums(directory)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-only", action="store_true")
    parser.add_argument("--zip-only", action="store_true")
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    version = (ROOT / "VERSION").read_text().strip()
    directory = args.directory or ROOT / f"artifacts/release/cloud-agent-release-{version}"
    if not args.zip_only:
        stage(directory)
    if not args.stage_only:
        spec = importlib.util.spec_from_file_location("release_deploy_manage", ROOT / "deploy/manage.py")
        manage = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(manage)
        manage.verify_checksums(directory)
        target = directory.parent / (directory.name + ".zip")
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(directory.parent))
        print(json.dumps({"zip": str(target), "bytes": target.stat().st_size}))
    else:
        print(json.dumps({"stage": str(directory)}))


if __name__ == "__main__":
    main()
