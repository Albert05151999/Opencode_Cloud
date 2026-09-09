"""Exercise baseline collection without claiming a real-provider baseline."""
import asyncio
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def check(state):
    baseline = load("model_baseline", "scripts/verify-model-baseline.py")
    report = await baseline.measure(
        "http://127.0.0.1:4001", 10,
        "LOCAL MOCK: baseline-client verification only; not external model acceptance",
        ROOT / "artifacts/perf/baseline-client-smoke",
    )
    assert report["result"] == "passed" and len(report["models"]) == 4
    assert report["ttft_metric_observation_delta"] >= 40
    print("baseline-client: four models x ten samples; TTFT metric observations verified")


if __name__ == "__main__":
    fixture = load("litellm_fixture", "scripts/verify-litellm.py")
    asyncio.run(fixture.verify(integration_hook=check, gateway_port=4001))
