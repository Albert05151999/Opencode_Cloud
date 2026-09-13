import asyncio
import copy
from pathlib import Path
import pytest
from fastapi import HTTPException
from operations.main import Workflows
from operations.src.store import Store
from operations.src.load_test_store import LoadTestStore, LoadRequest
from shared_libs.service import settings


def make_runtime(tmp_path):
    config = settings("operations")
    return Workflows(Store(tmp_path), config)


def test_request_identity_and_cross_process_target_lease(tmp_path):
    one, two = Store(tmp_path), Store(tmp_path)
    payload = {"request_id": "same-request"}
    job, created = one.submit("sandbox.stop", "sid", payload, scope="agent-a")
    assert created
    assert two.submit("sandbox.stop", "sid", payload, scope="agent-a") == (job, False)
    with pytest.raises(HTTPException):
        two.submit("agent.apply", "agent-a", {"request_id": "other"})
    with pytest.raises(HTTPException):
        two.submit("sandbox.stop", "sid", {"request_id": "same-request", "force": True})
    one.update(job["id"], status="needs_recovery")
    with pytest.raises(HTTPException):
        two.submit("agent.apply", "agent-a", {"request_id": "third"})


@pytest.mark.parametrize("failure", [None, "verify", "activate"])
def test_release_checkpoint_compensation_and_uncertain_outcome(tmp_path, failure):
    async def scenario():
        runtime = make_runtime(tmp_path)
        job, _ = runtime.store.submit(
            "models.apply", "*", {"request_id": "release-request"}
        )
        calls = []

        async def call(service, path, payload=None, method=None):
            calls.append(path)
            if path.endswith("/prepare"):
                return {"release_id": "release-1", "version": 2, "configuration": {}}
            if path.endswith("/activate") and failure == "activate":
                raise HTTPException(503, "lost activation response")
            if path.endswith("/status"):
                if failure == "verify":
                    raise HTTPException(503, "verification failed")
                return {"release_id": "release-1", "ready": True}
            return {"ok": True, "version": 2}

        runtime.call = call
        await runtime.run(job["id"])
        result = runtime.store.get(job["id"])
        if failure is None:
            assert result["status"] == "succeeded"
            assert result["checkpoint"] == "complete"
            assert calls.index("/internal/v1/config/activate") < calls.index(
                "/internal/v1/releases/release-1/commit"
            )
        elif failure == "verify":
            assert result["status"] == "failed" and result["compensated"]
            assert "/internal/v1/config/rollback" in calls
        else:
            assert result["status"] == "needs_recovery"
            assert "/internal/v1/config/rollback" not in calls
        await asyncio.gather(*(c.aclose() for c in runtime.clients.values()))

    asyncio.run(scenario())


def test_cancelled_job_cannot_enter_apply(tmp_path):
    async def scenario():
        runtime = make_runtime(tmp_path)
        job, _ = runtime.store.submit("models.apply", "*", {})
        actions = []

        async def call(service, path, payload=None, method=None):
            actions.append(path)
            if path.endswith("/prepare"):
                return {"release_id": "r", "configuration": {}}
            if path.endswith("/validate"):
                runtime.store.transition(job["id"], {"running"}, status="cancelled")
            return {"ok": True}

        runtime.call = call
        await runtime.run(job["id"])
        assert runtime.store.get(job["id"])["status"] == "cancelled"
        assert not any(p.endswith("/activate") for p in actions)
        await asyncio.gather(*(c.aclose() for c in runtime.clients.values()))

    asyncio.run(scenario())


def test_load_run_and_operations_admission_share_sqlite_lease(tmp_path):
    store = Store(tmp_path)
    loads = LoadTestStore(store)
    loads.catalog_snapshot = {
        "agents": {
            "agent-a": {
                "active": 1,
                "versions": [
                    {"version": 1, "config": {"enabled": True, "default_model_id": "m"}}
                ],
            }
        }
    }
    request = LoadRequest(request_id="test-request", agents=[{"agent_id": "agent-a"}])
    rid, created = loads.create(request)
    assert created
    assert loads.create(request) == (rid, False)
    with pytest.raises(HTTPException):
        store.submit("agent.apply", "agent-a", {})
    loads.update(rid, status="completed")
    store.submit("agent.apply", "agent-a", {"request_id": "apply-request"})
    with pytest.raises(HTTPException):
        loads.create(request.model_copy(update={"request_id": "other-request"}))


def test_load_cleanup_intent_survives_restart(tmp_path):
    store = Store(tmp_path)
    loads = LoadTestStore(store)
    loads.catalog_snapshot = {
        "agents": {
            "a": {
                "active": 1,
                "versions": [{"version": 1, "config": {"default_model_id": "m"}}],
            }
        }
    }
    rid, _ = loads.create(
        LoadRequest(request_id="load-request", agents=[{"agent_id": "a"}])
    )
    user = loads.get(rid)["users"][0]
    loads.update(rid, status="completed", cleanup_status="cleaning")
    loads.update_user(user["username"], storage_state="cleaning")
    restarted = LoadTestStore(Store(tmp_path))
    restarted.recover()
    assert restarted.get(rid)["cleanup_status"] == "failed"
    assert restarted.user("a", user["username"])["storage_state"] == "cleaning"


@pytest.mark.parametrize("verified", [False, True])
def test_reconcile_unknown_application_only_commits_verified_release(
    tmp_path, verified
):
    async def scenario():
        runtime = make_runtime(tmp_path)
        job, _ = runtime.store.submit(
            "models.apply", "*", {"request_id": "original-request"}
        )
        runtime.store.update(
            job["id"],
            status="needs_recovery",
            checkpoint="apply",
            release_id="release-1",
        )
        calls = []

        async def call(service, path, payload=None, method=None):
            calls.append((path, payload))
            if path.endswith("/releases/release-1"):
                return {"release_id": "release-1", "version": 2, "committed": False}
            if path.endswith("/status"):
                return {"ready": verified, "release_id": "release-1"}
            return {"version": 2, "ok": True}

        runtime.call = call
        if verified:
            assert (await runtime.reconcile(job["id"], "reconcile-request"))[
                "status"
            ] == "succeeded"
            assert any(path.endswith("/commit") for path, _ in calls)
            assert any(
                payload and payload.get("action") == "resume" for _, payload in calls
            )
        else:
            with pytest.raises(HTTPException):
                await runtime.reconcile(job["id"], "reconcile-request")
            assert runtime.store.get(job["id"])["status"] == "needs_recovery"
        assert not any(path.endswith(("/activate", "/rollback")) for path, _ in calls)
        await asyncio.gather(*(c.aclose() for c in runtime.clients.values()))

    asyncio.run(scenario())


def test_lost_commit_and_status_response_never_rolls_back_possibly_committed_release(
    tmp_path,
):
    async def scenario():
        runtime = make_runtime(tmp_path)
        job, _ = runtime.store.submit("models.apply", "*", {})
        calls = []

        async def call(service, path, payload=None, method=None):
            calls.append(path)
            if path.endswith("/prepare"):
                return {"release_id": "r", "version": 2, "configuration": {}}
            if path.endswith("/status"):
                return {"release_id": "r", "ready": True}
            if path.endswith(("/commit", "/releases/r")):
                raise HTTPException(503, "response lost")
            return {"ok": True}

        runtime.call = call
        await runtime.run(job["id"])
        assert runtime.store.get(job["id"])["status"] == "needs_recovery"
        assert not any(p.endswith("/rollback") for p in calls)
        await asyncio.gather(*(c.aclose() for c in runtime.clients.values()))

    asyncio.run(scenario())
