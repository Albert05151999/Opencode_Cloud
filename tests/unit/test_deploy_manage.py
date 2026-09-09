import configparser
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("deploy_manage", ROOT / "deploy/manage.py")
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)


def configuration(root):
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(ROOT / "config.cfg")
    cfg["platform"].update(host="127.0.0.1", data_root=str(root / "data"))
    cfg["storage"].update(workspace_root=str(root / "workspaces"), state_root=str(root / "state"))
    with (root / "config.cfg").open("w") as stream:
        cfg.write(stream)
    return cfg


def test_compose_env_file_is_not_overridden_by_shell(tmp_path, monkeypatch):
    configuration(tmp_path)
    (tmp_path / ".env").write_text("MINIMAX_API_KEY=file-value\nCODING_FAST_API_KEY=${MINIMAX_API_KEY}\n")
    monkeypatch.setenv("MINIMAX_API_KEY", "unwanted-shell-value")
    monkeypatch.setenv("CODING_FAST_API_KEY", "unwanted-shell-value")
    captured = {}
    monkeypatch.setattr(manage, "run", lambda args, **kwargs: captured.update(kwargs))
    manage.compose(tmp_path, "up", "-d")
    assert "MINIMAX_API_KEY" not in captured["env"]
    assert "CODING_FAST_API_KEY" not in captured["env"]


def test_changed_instance_cannot_orphan_previous_containers(tmp_path):
    configuration(tmp_path)
    (tmp_path / ".instance-id").write_text("another-instance")
    with pytest.raises(RuntimeError, match="restore_original_instance_id"):
        manage.read_config(tmp_path)


def test_existing_listener_preserved_until_explicit_override(tmp_path):
    cfg = configuration(tmp_path)
    before = (tmp_path / "config.cfg").read_bytes()
    manage.configure_listener(tmp_path)
    assert (tmp_path / "config.cfg").read_bytes() == before
    manage.configure_listener(tmp_path, "0.0.0.0", 18080)
    actual = manage.read_config(tmp_path)
    assert actual["platform"]["host"] == "0.0.0.0"
    assert actual.getint("platform", "port") == 18080
    assert actual["platform"]["instance_id"] == cfg["platform"]["instance_id"]
    assert dict(actual["storage"]) == dict(cfg["storage"])
    assert next(tmp_path.glob("config.cfg.before-listener-*")).read_bytes() == before


def test_new_install_uses_bundle_listener(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    (bundle / "config").mkdir(parents=True)
    cfg = configuration(bundle / "config")
    cfg["platform"].update(host="0.0.0.0", port="18080")
    with (bundle / "config/config.cfg").open("w") as stream:
        cfg.write(stream)
    monkeypatch.setattr(manage, "BUNDLE", bundle)
    root = tmp_path / "install"
    root.mkdir()
    manage.configure_listener(root)
    actual = manage.read_config(root)
    assert actual["platform"]["host"] == "0.0.0.0"
    assert actual.getint("platform", "port") == 18080
    assert actual["platform"]["data_root"] == str(root / "data")


def test_bundle_checksum_rejects_tampering_and_parent_path(tmp_path):
    content = tmp_path / "VERSION"
    content.write_bytes(b"0.1.0")
    digest = hashlib.sha256(content.read_bytes()).hexdigest()
    manifest = tmp_path / "checksums.sha256"
    manifest.write_text(digest + "  VERSION\n")
    manage.verify_checksums(tmp_path)
    content.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="checksum_mismatch"):
        manage.verify_checksums(tmp_path)
    manifest.write_text(digest + "  ../" + tmp_path.name + "/../\n")
    with pytest.raises(RuntimeError, match="invalid_checksum_path"):
        manage.verify_checksums(tmp_path)


def test_controller_mounts_exclude_provider_env(tmp_path, monkeypatch):
    configuration(tmp_path)
    names = ["cloud-agent-controller", "cloud-agent-runtime", "model-gateway", "prometheus", "grafana"]
    (tmp_path / "release-images.json").write_text(json.dumps({"images": {n: {"id": "sha256:" + "a" * 64} for n in names}}))
    monkeypatch.setattr(manage, "run", lambda *a, **kw: SimpleNamespace(stdout='[{"IPAM":{"Config":[{"Gateway":"172.30.0.1"}]}}]'))
    monkeypatch.setattr(manage.os, "chown", lambda *a, **kw: None)
    manage.render(tmp_path)
    services = json.loads((tmp_path / "deploy/compose.generated.json").read_text())["services"]
    mounts = services["controller"]["volumes"]
    assert not any(".env" in value or value.split(":")[0] == str(tmp_path) for value in mounts)
    assert all(service["pull_policy"] == "never" for service in services.values())
    assert "API_KEY" not in json.dumps(services["controller"])
    assert "${CODING_FAST_API_KEY:" in services["model-gateway"]["environment"]["CODING_FAST_API_KEY"]


def test_portable_digest_resolves_classic_docker_store(tmp_path, monkeypatch):
    index_id, config_id = "sha256:" + "a" * 64, "sha256:" + "b" * 64
    (tmp_path / "release-images.json").write_text(json.dumps({"images": {"runtime": {"id": index_id, "portable_id": config_id}}}))
    def inspect(command, **kwargs):
        return SimpleNamespace(returncode=0 if command[-1] == config_id else 1,
                               stdout=json.dumps([{"Id": config_id}]))
    monkeypatch.setattr(manage.subprocess, "run", inspect)
    image = manage.resolve_images(tmp_path)["images"]["runtime"]
    assert image["id"] == config_id
    assert image["source_id"] == index_id
