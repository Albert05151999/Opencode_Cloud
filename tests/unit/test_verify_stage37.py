import importlib.util
import json
import zipfile
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify-stage37.py"
SPEC = importlib.util.spec_from_file_location("verify_stage37", SCRIPT)
stage37 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage37)


def package(zip_sha="abc"):
    return {
        "zip_sha256": zip_sha,
        "steps": [{"name": name, "exit_code": 0} for name in (
            "install", "smoke", "restart", "status", "marker_after_restart",
            "uninstall", "inner_containers_empty", "marker_retained", "config_retained", "env_retained")],
        "initial_images_empty": True,
        "no_development_checkout_mount": True,
        "resources": {"swap_current_bytes": 0, "oom_killed": False},
        "smoke": {"result": "passed", "burst": {"requests": 8, "successes": 8, "failures": []}},
    }


def test_package_requires_exact_zip_digest_and_burst():
    stage37.validate_package(package(), "abc")
    with pytest.raises(stage37.EvidenceError, match="zip_digest_mismatch"):
        stage37.validate_package(package(), "tampered")
    bad = package()
    bad["smoke"]["burst"]["successes"] = 7
    with pytest.raises(stage37.EvidenceError, match="package_burst_invalid"):
        stage37.validate_package(bad, "abc")


def test_missing_evidence_never_defaults_to_pass(tmp_path):
    with pytest.raises(stage37.EvidenceError, match="evidence_missing"):
        stage37.load_passed(tmp_path / "missing.json")


def test_source_fingerprint_changes_after_tamper(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "agents").mkdir()
    (tmp_path / "config").mkdir()
    for relative in ("config.cfg", "pyproject.toml", "config/litellm_config.yaml", "app/main.py"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("before")
    before = stage37.source_fingerprint(tmp_path)
    (tmp_path / "app/main.py").write_text("after")
    assert stage37.source_fingerprint(tmp_path) != before


def test_zip_contents_reject_document_or_image_mixing(tmp_path):
    (tmp_path / "01_architecture.md").write_bytes("架构".encode())
    (tmp_path / "02_api_contract.md").write_bytes("契约".encode())
    expected = {"cloud-agent-runtime": "sha256:runtime"}
    package = tmp_path / "release.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("cloud-agent-release-1/01_architecture.md", "架构")
        archive.writestr("cloud-agent-release-1/02_api_contract.md", "契约")
        archive.writestr("cloud-agent-release-1/release-images.json", json.dumps({"images": {"cloud-agent-runtime": {"id": "sha256:old"}}}))
    with pytest.raises(stage37.EvidenceError, match="zip_image_identity_mismatch"):
        stage37.validate_zip_contents(package, tmp_path, expected)
