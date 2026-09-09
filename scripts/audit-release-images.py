#!/usr/bin/env python3
"""Audit production image metadata without retaining potentially sensitive text."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "release" / "image-audit.json"
IMAGE_NAMES = ("cloud-agent-runtime", "cloud-agent-controller", "model-gateway")
SENSITIVE_NAME = re.compile(r"(?:^|_)(?:API_KEY|TOKEN|SECRET|PASSWORD)(?:$|_)", re.I)
SENSITIVE_ASSIGNMENT = re.compile(
    r"(?:^|[\s\"'])((?:[A-Za-z0-9]+_)*(?:API_KEY|TOKEN|SECRET|PASSWORD)(?:_[A-Za-z0-9]+)*)=([^\s\"']*)",
    re.I,
)
DEVELOPMENT_HOME = re.compile(
    r"(?:[A-Za-z]:[\\/]Users[\\/][^\\/\s]+|/Users/[^/\s]+|"
    r"/home/(?:zephyrusg14|runner|developer|dev|ubuntu|vscode|codespace|[^/\s]*admin[^/\s]*)(?:/|$))",
    re.I,
)


def is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        not normalized
        or normalized in {"unset", "none", "null", "changeme", "change-me", "placeholder", "redacted"}
        or (normalized.startswith("${") and normalized.endswith("}"))
        or (normalized.startswith("<") and normalized.endswith(">"))
        or (normalized.startswith("__") and normalized.endswith("__"))
    )


def parse_env_file(path: Path) -> list[str]:
    """Return sensitive values in memory; never return names or source lines."""
    if not path.is_file():
        return []
    values: list[str] = []
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.removeprefix("export ").split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[:1] == value[-1:] and value[0] in "\"'":
            value = value[1:-1]
        if SENSITIVE_NAME.search(name.strip()) and not is_placeholder(value):
            values.append(value)
    return values


def iter_text(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from iter_text(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from iter_text(nested)


def scan(inspect_data: dict[str, Any], history: list[dict[str, Any]], actual_secrets: list[str]) -> set[str]:
    errors: set[str] = set()
    config = inspect_data.get("Config") or {}
    for item in config.get("Env") or []:
        name, separator, value = item.partition("=")
        if separator and SENSITIVE_NAME.search(name) and not is_placeholder(value):
            errors.add("embedded_sensitive_env")

    history_text = list(iter_text(history))
    for item in history_text:
        for match in SENSITIVE_ASSIGNMENT.finditer(item):
            if not is_placeholder(match.group(2)):
                errors.add("embedded_sensitive_env")

    text = list(iter_text(inspect_data))
    text.extend(history_text)
    if any(DEVELOPMENT_HOME.search(item) for item in text):
        errors.add("development_home_path")
    if actual_secrets and any(secret in item for item in text for secret in actual_secrets):
        errors.add("embedded_env_secret")
    return errors


def docker_json(arguments: list[str]) -> Any:
    completed = subprocess.run(
        ["docker", *arguments], check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return json.loads(completed.stdout)


def inspect_image(reference: str, actual_secrets: list[str]) -> tuple[dict[str, Any], set[str]]:
    inspected = docker_json(["image", "inspect", reference])[0]
    completed = subprocess.run(
        ["docker", "image", "history", "--no-trunc", "--format", "{{json .}}", reference],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    history = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    errors = scan(inspected, history, actual_secrets)
    result = {
        "reference": reference,
        "image_id": inspected.get("Id"),
        "size_bytes": inspected.get("Size"),
        "history_layers": len(history),
        "passed": not errors,
    }
    return result, errors


def write_report(report: dict[str, Any]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    actual_secrets = parse_env_file(ROOT / "deploy" / ".env")
    images: list[dict[str, Any]] = []
    errors: set[str] = set()
    try:
        for name in IMAGE_NAMES:
            result, found = inspect_image(f"{name}:{version}", actual_secrets)
            images.append(result)
            errors.update(found)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, IndexError, KeyError):
        errors.add("image_inspection_failed")

    if errors:
        write_report({"result": "failed", "errors": sorted(errors)})
        for category in sorted(errors):
            print(category, file=sys.stderr)
        return 1
    write_report({"result": "passed", "version": version, "images": images})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
