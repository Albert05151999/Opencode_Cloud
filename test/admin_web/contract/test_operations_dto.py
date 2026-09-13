"""Frontend-required shapes produced by the actual operations API/store."""

import asyncio
import time
import httpx


def test_jobs_and_load_reports_match_frontend_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", "token")
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "default"))
    from operations.main import create_app
    from operations.src.load_test_store import LoadRequest

    async def scenario():
        app = create_app(tmp_path / "operations")
        runtime = app.state.runtime

        async def dependency(service, path, payload=None, method=None):
            if path.endswith("/load-test-catalog"):
                return {
                    "agents": {
                        "a": {
                            "id": "a",
                            "active": 1,
                            "versions": [
                                {
                                    "version": 1,
                                    "config": {
                                        "name": "Agent",
                                        "enabled": True,
                                        "default_model_id": "m",
                                    },
                                }
                            ],
                        }
                    }
                }
            if path.endswith("/capacity"):
                return {
                    "known": True,
                    "sampled_at": time.time(),
                    "admission_allowed": True,
                    "remaining_cpu": 8,
                    "remaining_memory_mb": 8192,
                }
            raise AssertionError(path)

        runtime.call = dependency
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app),
                base_url="http://operations",
                headers={"Authorization": "Bearer token"},
            ) as client:
                options = (await client.get("/cloud/admin/load-tests/options")).json()
                assert {"id", "name", "version", "model_id"} <= options["agents"][
                    0
                ].keys()
                assert {
                    "max_users",
                    "defaults",
                    "prompt",
                    "host_capacity",
                } <= options.keys()
                rid, _ = runtime.load_tests.store.create(
                    LoadRequest(
                        request_id="dto-load",
                        agents=[
                            {
                                "agent_id": "a",
                                "users": 1,
                                "cpu_limit": 1,
                                "memory_mb": 1024,
                            }
                        ],
                    )
                )
                listing = (await client.get("/cloud/admin/load-tests")).json()
                assert {
                    "items",
                    "total",
                    "active_id",
                    "offset",
                    "limit",
                } <= listing.keys()
                report = (await client.get("/cloud/admin/load-tests/" + rid)).json()
                assert {
                    "id",
                    "created_at",
                    "status",
                    "cleanup_status",
                    "summary",
                    "by_agent",
                    "users",
                } <= report.keys()
                assert {
                    "users",
                    "submitted",
                    "succeeded",
                    "failed",
                    "p95_ms",
                } <= report["summary"].keys()
                job, _ = app.state.store.submit(
                    "sandbox.restart",
                    "sbx_other",
                    {"request_id": "dto-job", "secret": "private"},
                    scope="other-agent",
                )
                result = (await client.get("/cloud/admin/jobs/" + job["id"])).json()
                assert {"id", "kind", "target", "status"} <= result.keys()
                assert (
                    result["target"] == "other-agent"
                    and result["resource_id"] == "sbx_other"
                )
                assert "payload" not in result and "private" not in str(result)
        finally:
            await asyncio.gather(
                *(client.aclose() for client in runtime.clients.values())
            )

    asyncio.run(scenario())
