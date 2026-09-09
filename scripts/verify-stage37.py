#!/usr/bin/env python3
"""Aggregate immutable release evidence without rerunning acceptance workloads."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "release" / "final-acceptance.json"
REPORTS = {
    "image_build": "artifacts/release/image-build.json",
    "image_audit": "artifacts/release/image-audit.json",
    "controller_image": "artifacts/release/controller-smoke.json",
    "package_verification": "artifacts/release/package-verification.json",
    "performance": "artifacts/perf/stage29-report.json",
    "sse": "artifacts/sse/report.json",
    "v2_sse": "artifacts/sse/v2-report.json",
}


class EvidenceError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_passed(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EvidenceError("evidence_missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError("evidence_invalid") from exc
    if not isinstance(value, dict) or value.get("result") != "passed":
        raise EvidenceError("evidence_not_passed")
    return value


def source_fingerprint(root: Path) -> dict[str, str]:
    paths = [root / "config.cfg", root / "pyproject.toml", root / "config/litellm_config.yaml"]
    paths += list((root / "app").glob("*.py"))
    paths += [p for p in (root / "agents").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    return {str(path.relative_to(root)): sha256(path) for path in sorted(paths)}


def validate_package(report: dict[str, Any], zip_digest: str) -> None:
    smoke = report.get("smoke") or {}
    burst = smoke.get("burst") or {}
    resources = report.get("resources") or {}
    steps = report.get("steps")
    if report.get("zip_sha256") != zip_digest:
        raise EvidenceError("zip_digest_mismatch")
    if not isinstance(steps, list) or not steps or any(step.get("exit_code") != 0 for step in steps):
        raise EvidenceError("package_step_failed")
    required_steps = {"install", "smoke", "restart", "status", "marker_after_restart",
                      "uninstall", "inner_containers_empty", "marker_retained", "config_retained", "env_retained"}
    if not required_steps <= {step.get("name") for step in steps}:
        raise EvidenceError("package_steps_missing")
    if smoke.get("result") != "passed" or burst.get("requests") != 8 or burst.get("successes") != 8 or burst.get("failures") != []:
        raise EvidenceError("package_burst_invalid")
    if resources.get("swap_current_bytes") != 0 or resources.get("oom_killed") is not False:
        raise EvidenceError("package_resources_invalid")
    if report.get("initial_images_empty") is not True or report.get("no_development_checkout_mount") is not True:
        raise EvidenceError("package_isolation_invalid")
    if report.get("cleanup_errors") not in (None, []):
        raise EvidenceError("package_cleanup_failed")


def validate_chinese_document(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise EvidenceError("document_missing")
    if not re.search(r"[\u3400-\u9fff]", path.read_text(encoding="utf-8")):
        raise EvidenceError("document_not_chinese")


def current_image_ids(build: dict[str, Any]) -> dict[str, str]:
    observed = {}
    for name, metadata in build["images"].items():
        raw = subprocess.run(
            ["docker", "image", "inspect", metadata["tag"], "--format", "{{.Id}}"],
            check=True, capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()
        if not raw.startswith("sha256:"):
            raise EvidenceError("production_image_missing")
        observed[name] = raw
    return observed


def validate_zip_contents(
    zip_path: Path, root: Path, expected_ids: dict[str, str]
) -> dict[str, str]:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            files = [name for name in archive.namelist() if name and not name.endswith("/")]
            roots = {name.split("/", 1)[0] for name in files if "/" in name}
            if len(roots) != 1:
                raise EvidenceError("zip_root_invalid")
            prefix = next(iter(roots))
            for document in ("01_architecture.md", "02_api_contract.md"):
                if archive.read(f"{prefix}/{document}") != (root / document).read_bytes():
                    raise EvidenceError("zip_document_mismatch")
            manifest = json.loads(archive.read(f"{prefix}/release-images.json"))
    except EvidenceError:
        raise
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise EvidenceError("zip_content_invalid") from exc
    images = manifest.get("images") or {}
    zip_ids = {name: (images.get(name) or {}).get("id") for name in expected_ids}
    if zip_ids != expected_ids:
        raise EvidenceError("zip_image_identity_mismatch")
    return zip_ids


def aggregate(root: Path, zip_path: Path) -> dict[str, Any]:
    evidence = {name: load_passed(root / relative) for name, relative in REPORTS.items()}
    input_sha = {relative: sha256(root / relative) for relative in REPORTS.values()}
    zip_digest = sha256(zip_path)
    stage29 = evidence["performance"]
    if stage29.get("source_sha256") != source_fingerprint(root):
        raise EvidenceError("performance_source_mismatch")
    component_evidence = stage29.get("evidence")
    if not isinstance(component_evidence, dict) or len(component_evidence) != 3:
        raise EvidenceError("performance_components_missing")
    for filename, digest in component_evidence.items():
        if sha256(root / filename) != digest:
            raise EvidenceError("performance_component_digest_mismatch")
    validate_package(evidence["package_verification"], zip_digest)
    validate_chinese_document(root / "01_architecture.md")
    validate_chinese_document(root / "02_api_contract.md")

    build_images = evidence["image_build"].get("images") or {}
    if set(build_images) != {"cloud-agent-runtime", "cloud-agent-controller", "model-gateway"}:
        raise EvidenceError("build_image_set_invalid")
    expected_ids = {name: item.get("id") for name, item in build_images.items()}
    if any(not isinstance(value, str) or not value.startswith("sha256:") for value in expected_ids.values()):
        raise EvidenceError("build_image_id_invalid")
    zip_image_ids = validate_zip_contents(zip_path, root, expected_ids)
    audit_ids = {
        item.get("reference", "").split(":", 1)[0]: item.get("image_id")
        for item in evidence["image_audit"].get("images", []) if item.get("passed") is True
    }
    if audit_ids != expected_ids:
        raise EvidenceError("image_audit_identity_mismatch")
    controller = evidence["controller_image"].get("images") or {}
    if (controller.get("controller") or {}).get("id") != expected_ids["cloud-agent-controller"] or (controller.get("runtime") or {}).get("id") != expected_ids["cloud-agent-runtime"]:
        raise EvidenceError("controller_evidence_identity_mismatch")
    observed_ids = current_image_ids(evidence["image_build"])
    if observed_ids != expected_ids:
        raise EvidenceError("production_image_identity_mismatch")

    package = evidence["package_verification"]
    return {
        "result": "passed",
        "zip_sha256": zip_digest,
        "input_sha256": input_sha,
        "production_image_ids": observed_ids,
        "zip_production_image_ids": zip_image_ids,
        "package_image_ids": package["image_ids"],
        "performance_measurements": stage29["gates"],
        "production_burst": package["smoke"]["burst"],
        "gates": {
            "all_reports_passed": True,
            "performance_source_current": True,
            "zip_matches_clean_acceptance": True,
            "package_burst_8_of_8": True,
            "package_swap_current_zero": True,
            "package_oom_killed_false": True,
            "package_cleanup_succeeded": True,
            "production_images_match_build": True,
            "zip_images_and_documents_match_current_release": True,
            "chinese_documents_present": True,
        },
        "evidence_scope": {
            "performance": "same-version source fingerprint and controlled runtime measurements",
            "production_topology": "independent clean ZIP installation with an eight-request model burst",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, required=True)
    args = parser.parse_args()
    try:
        if not args.zip.is_file():
            raise EvidenceError("zip_missing")
        report = aggregate(ROOT, args.zip.resolve())
    except EvidenceError as exc:
        report = {"result": "failed", "error_category": str(exc)}
    except (OSError, KeyError, TypeError, subprocess.SubprocessError):
        report = {"result": "failed", "error_category": "evidence_check_failed"}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": report["result"], "output": str(OUTPUT)}))
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
