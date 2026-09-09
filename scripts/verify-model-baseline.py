#!/usr/bin/env python3
"""Measure a running, configured model gateway without OpenCode overhead."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


async def measure(base_url: str, rounds: int, source_label: str, output: Path):
    if rounds < 10:
        raise ValueError("baseline requires at least 10 samples per logical model")
    spec = importlib.util.spec_from_file_location("load_client", ROOT / "tests/load/run_load.py")
    load = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(load)
    output.mkdir(parents=True, exist_ok=True)
    report = {"result": "running", "source_label": source_label, "started_at": datetime.now(timezone.utc).isoformat(), "samples_per_model": rounds, "models": {}}
    async with httpx.AsyncClient(base_url=base_url, trust_env=False, timeout=15, follow_redirects=True) as http:
        health = await http.get("/health/liveliness")
        health.raise_for_status()
        before = await http.get("/metrics/")
        before.raise_for_status()
        (output / "direct-model-metrics-before.prom").write_text(before.text)
        try:
            for agent, names in [("agent-code", ["coding-fast", "coding-quality"]), ("agent-data", ["data-fast", "data-quality"])]:
                for name in names:
                    summary = await load.run(base_url, rounds=rounds, mode="model", matrix=[(agent, "baseline", name)], output=output / f"direct-model-{name}")
                    report["models"][name] = summary
                    if summary["failures"]:
                        raise RuntimeError(f"{name} baseline contains failed requests")
            after = await http.get("/metrics/")
            after.raise_for_status()
            (output / "direct-model-metrics-after.prom").write_text(after.text)
            from prometheus_client.parser import text_string_to_metric_families
            def ttft_count(text):
                return sum(sample.value for family in text_string_to_metric_families(text) for sample in family.samples if sample.name == "litellm_llm_api_time_to_first_token_metric_count")
            count = ttft_count(after.text) - ttft_count(before.text)
            assert count >= 4 * rounds, f"missing TTFT observations: {count}"
            report["ttft_metric_observation_delta"] = count
            report["result"] = "passed"
        except Exception as exc:
            report.update(result="failed", error=type(exc).__name__)
            raise
        finally:
            (output / "direct-model-baseline.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:4001")
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--source-label", required=True, help="Non-secret provider/deployment description recorded as provenance")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/perf")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(measure(args.base_url, args.rounds, args.source_label, args.output)), indent=2))
