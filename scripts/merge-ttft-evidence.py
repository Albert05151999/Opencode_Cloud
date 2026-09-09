#!/usr/bin/env python3
"""Merge complete gateway TTFT model groups without hiding failed attempts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "artifacts" / "perf" / "gateway-ttft"
LOGICAL_MODELS = ("coding-fast", "coding-quality", "data-fast", "data-quality")
SAMPLES_PER_MODEL = 20
NEGATIVE_TOLERANCE_MS = 5.0
REQUIRED_CSV_FIELDS = (
    "request_id", "logical_model", "slot", "model_id", "gateway_ttft_ms",
    "physical_ttft_ms", "paired_overhead_ms", "litellm_overhead_header_ms",
    "litellm_overhead_header_available", "attempted_retries", "attempted_fallbacks",
    "status", "error",
)
CSV_FIELDS = REQUIRED_CSV_FIELDS + ("relay_attempts",)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def required_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"missing or invalid {name}")
    return value


def load_source(report_path: Path) -> dict[str, Any]:
    report_path = report_path.resolve(strict=True)
    report = required_mapping(json.loads(report_path.read_text(encoding="utf-8")), "report")
    if not isinstance(report.get("result"), str):
        raise ValueError(f"missing result in {report_path}")
    if report.get("cleanup_errors"):
        raise ValueError(f"source has cleanup errors: {report_path}")
    config = required_mapping(report.get("config"), "config")
    image = required_mapping(report.get("image"), "image")
    if not isinstance(config.get("sha256"), str) or not config["sha256"]:
        raise ValueError(f"missing config.sha256 in {report_path}")
    if not isinstance(image.get("id"), str) or not image["id"]:
        raise ValueError(f"missing image.id in {report_path}")
    if image.get("same_image_id") is not True:
        raise ValueError(f"image.same_image_id is not true in {report_path}")
    csv_path = report_path.with_name("samples.csv")
    csv_path.resolve(strict=True)
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or any(field not in reader.fieldnames for field in REQUIRED_CSV_FIELDS):
            raise ValueError(f"missing required CSV fields in {csv_path}")
        rows = list(reader)
        for row in rows:
            row.setdefault("relay_attempts", "[]")
    unknown = sorted({row["logical_model"] for row in rows} - set(LOGICAL_MODELS))
    if unknown:
        raise ValueError(f"unknown logical models in {csv_path}: {unknown}")
    return {
        "report_path": report_path,
        "csv_path": csv_path,
        "report": report,
        "rows": rows,
    }


def validate_group(rows: list[dict[str, str]]) -> tuple[list[str], int, list[float]]:
    reasons: list[str] = []
    failures = sum(row["status"] != "passed" for row in rows)
    if len(rows) != SAMPLES_PER_MODEL:
        reasons.append(f"sample_count={len(rows)}")
    if failures:
        reasons.append(f"failed_samples={failures}")
    request_ids = [row["request_id"] for row in rows]
    if any(not value for value in request_ids) or len(set(request_ids)) != len(request_ids):
        reasons.append("invalid_or_duplicate_request_id")
    overheads: list[float] = []
    for row in rows:
        try:
            overhead = float(row["paired_overhead_ms"])
            gateway_ttft = float(row["gateway_ttft_ms"])
            physical_ttft = float(row["physical_ttft_ms"])
            slot = int(row["slot"])
            retries = int(row["attempted_retries"])
            fallbacks = int(row["attempted_fallbacks"])
        except (TypeError, ValueError):
            reasons.append("invalid_numeric_field")
            continue
        if not math.isfinite(overhead):
            reasons.append("nonfinite_paired_overhead")
        elif overhead < -NEGATIVE_TOLERANCE_MS:
            reasons.append("paired_overhead_below_tolerance")
        else:
            overheads.append(overhead)
        if not math.isfinite(gateway_ttft) or not math.isfinite(physical_ttft):
            reasons.append("nonfinite_ttft")
        elif gateway_ttft < 0 or physical_ttft < 0:
            reasons.append("negative_ttft")
        elif math.isfinite(overhead) and abs((gateway_ttft - physical_ttft) - overhead) > 0.001:
            reasons.append("inconsistent_paired_overhead")
        if slot not in (1, 2) or row["model_id"] != f"{row['logical_model']}-{slot}":
            reasons.append("model_slot_mismatch")
        if retries != 0 or fallbacks != 0:
            reasons.append("retry_or_fallback")
    return sorted(set(reasons)), failures, overheads


def merge(report_paths: list[Path]) -> Path:
    sources = [load_source(path) for path in report_paths]
    if not sources:
        raise ValueError("at least one report is required")
    config_hashes = {source["report"]["config"]["sha256"] for source in sources}
    image_ids = {source["report"]["image"]["id"] for source in sources}
    if len(config_hashes) != 1:
        raise ValueError("source config.sha256 values differ")
    if len(image_ids) != 1:
        raise ValueError("source image.id values differ")

    selected: dict[str, tuple[dict[str, Any], list[dict[str, str]], list[float]]] = {}
    excluded: list[dict[str, Any]] = []
    source_audit: list[dict[str, Any]] = []
    for source in sources:
        source_audit.append({
            "report": str(source["report_path"]),
            "report_sha256": sha256(source["report_path"]),
            "csv": str(source["csv_path"]),
            "csv_sha256": sha256(source["csv_path"]),
            "original_result": source["report"]["result"],
        })
        for logical in LOGICAL_MODELS:
            rows = [row for row in source["rows"] if row["logical_model"] == logical]
            reasons, failures, overheads = validate_group(rows)
            if reasons:
                excluded.append({
                    "model": logical,
                    "report": str(source["report_path"]),
                    "samples": len(rows),
                    "failed_samples": failures,
                    "reasons": reasons,
                })
                continue
            if logical in selected:
                previous = selected[logical][0]
                excluded.append({
                    "model": logical,
                    "report": str(previous["report_path"]),
                    "samples": SAMPLES_PER_MODEL,
                    "failed_samples": 0,
                    "reasons": ["superseded_by_later_qualified_source"],
                })
            selected[logical] = (source, rows, overheads)

    missing = [logical for logical in LOGICAL_MODELS if logical not in selected]
    if missing:
        raise ValueError(f"no qualified complete group for models: {missing}")
    merged_rows = [row for logical in LOGICAL_MODELS for row in selected[logical][1]]
    request_ids = [row["request_id"] for row in merged_rows]
    if len(merged_rows) != 80 or len(set(request_ids)) != 80:
        raise ValueError("merged evidence must contain 80 unique request IDs")

    models: dict[str, Any] = {}
    for logical in LOGICAL_MODELS:
        source, _, overheads = selected[logical]
        p95 = percentile(overheads, 0.95)
        models[logical] = {
            "samples": SAMPLES_PER_MODEL,
            "paired_overhead_p50_ms": percentile(overheads, 0.50),
            "paired_overhead_p95_ms": p95,
            "minimum_paired_overhead_ms": min(overheads),
            "maximum_paired_overhead_ms": max(overheads),
            "passed": p95 <= 300,
            "selected_source_report": str(source["report_path"]),
        }
    if not all(model["passed"] for model in models.values()):
        raise ValueError("one or more selected model groups exceed 300ms p95")

    now = datetime.now(timezone.utc)
    output = OUTPUT_ROOT / ("run-" + now.strftime("%Y%m%d-%H%M%S-%f") + "-merged")
    output.mkdir(parents=True, exist_ok=False)
    with (output / "samples.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged_rows)
    first_report = sources[0]["report"]
    report = {
        "result": "passed",
        "started_at": now.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "samples_per_model": SAMPLES_PER_MODEL,
        "negative_tolerance_ms": NEGATIVE_TOLERANCE_MS,
        "scope": "Merged only complete qualified 20-sample model groups; excluded attempts remain audited below.",
        "config": first_report["config"],
        "image": first_report["image"],
        "models": models,
        "merge_audit": {
            "selection_rule": "The last qualified complete source group for each model is selected.",
            "sources": source_audit,
            "excluded_groups": excluded,
        },
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return output / "report.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    try:
        report_path = merge(args.reports)
        print(json.dumps({"result": "passed", "report": str(report_path)}))
    except Exception as exc:
        print(json.dumps({"result": "failed", "error": type(exc).__name__, "message": str(exc)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
