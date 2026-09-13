import asyncio
import copy
import time
import pytest
from pydantic import ValidationError
from operations.src.recovery import Recovery, RecoveryPolicy
from operations.main import Workflows
from operations.src.store import Store
from shared_libs.service import settings


def test_policy_rejects_unbounded_recovery_inputs():
    for values in (
        {"backoff_seconds": [0]},
        {"max_parallel_recoveries": 3},
        {"max_attempts": 11},
        {"unknown": True},
    ):
        with pytest.raises(ValidationError):
            RecoveryPolicy(**values)


def test_recovery_requires_unchanged_idle_evidence_and_persists_attempts(tmp_path):
    async def scenario():
        runtime = Workflows(Store(tmp_path), settings("operations"))
        recovery = Recovery(runtime)
        runtime.store.state("recovery-policy", {"failure_threshold": 1})
        record = {
            "sandbox_id": "sid",
            "agent_id": "a",
            "username": "u",
            "container_id": "container",
            "status": "ready",
        }
        detail = {"execution": "idle", "activity_generation": 12}

        async def call(service, path, payload=None, method=None):
            if "/sandboxes?" in path:
                return {"items": [copy.deepcopy(record)]}
            if path.endswith("/load-test-catalog"):
                return {"agents": {"a": {"lifecycle": "active"}}}
            return copy.deepcopy(detail)

        runtime.call = call
        spawned = []
        runtime.spawn = spawned.append
        await recovery.tick()
        assert recovery.state("sid")["execution"] == "idle"
        record["status"] = "missing"
        detail["execution"] = "unknown"
        detail["activity_generation"] = 13
        await recovery.tick()
        assert not spawned and "unknown" in recovery.state("sid")["reason"]
        detail["activity_generation"] = 12
        await recovery.tick()
        assert len(spawned) == 1
        job = runtime.store.get(spawned[0])
        assert job["kind"] == "sandbox.recover"
        restarted = Recovery(Workflows(Store(tmp_path), settings("operations")))
        assert len(restarted.state("sid")["attempts"]) == 1
        await asyncio.gather(
            *(c.aclose() for c in runtime.clients.values()),
            *(c.aclose() for c in restarted.runtime.clients.values()),
        )

    asyncio.run(scenario())
