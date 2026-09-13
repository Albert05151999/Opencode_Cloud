import asyncio
import copy
import time
import httpx
from fastapi import HTTPException
from operations.main import create_app


def test_agent_delete_preview_guards_all_owners_and_duplicate_request(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SERVICE_TOKEN", "token")

    async def scenario():
        app = create_app(tmp_path)
        runtime = app.state.runtime
        catalog = {
            "agent_id": "a",
            "revision": 2,
            "lifecycle": "archived",
            "private_resources": ["private"],
            "fingerprint": "cat",
        }
        file = {"files": 2, "bytes": 10, "fingerprint": "file"}
        sandbox = {"sandboxes": ["s"], "sessions": 2, "fingerprint": "sandbox"}
        calls = []

        async def call(service, path, payload=None, method=None):
            calls.append((service, path, payload))
            if path.endswith("/deletion-impact"):
                return copy.deepcopy(
                    {
                        "catalog_service": catalog,
                        "file_service": file,
                        "sandbox_manager": sandbox,
                    }[service]
                )
            return {"ok": True}

        runtime.call = call
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app),
            base_url="http://operations",
            headers={"Authorization": "Bearer token"},
        ) as client:
            preview = (await client.get("/cloud/admin/agents/a/delete-preview")).json()
            assert preview["files"] == 2 and preview["private_resources"] == ["private"]
            payload = {
                "request_id": "delete-request",
                "confirmation": "a",
                "preview_id": preview["preview_id"],
            }
            file["fingerprint"] = "changed"
            assert (
                await client.post("/cloud/admin/agents/a/delete", json=payload)
            ).status_code == 409
            file["fingerprint"] = "file"
            result = await client.post("/cloud/admin/agents/a/delete", json=payload)
            assert result.status_code == 200, result.text
            await asyncio.gather(*runtime.tasks)
            jid = result.json()["job_id"]
            assert app.state.store.get(jid)["status"] == "succeeded"
            # Retrying the same HTTP intent never repeats deletion/preview reads.
            before = len(calls)
            assert (
                await client.post("/cloud/admin/agents/a/delete", json=payload)
            ).json() == result.json()
            assert len(calls) == before
            cleanup = next(
                p
                for s, path, p in calls
                if s == "file_service" and path.endswith("/cleanup")
            )
            assert cleanup["expected_fingerprint"] == "file"
        await asyncio.gather(*(c.aclose() for c in runtime.clients.values()))

    asyncio.run(scenario())


def test_load_executes_http_sessions_reports_and_cleanup_blocks_reacquire(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SERVICE_TOKEN", "token")

    async def scenario():
        app = create_app(tmp_path)
        runtime = app.state.runtime
        load = runtime.load_tests
        calls = []

        async def call(service, path, payload=None, method=None):
            calls.append((service, path, payload))
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
                                        "name": "A",
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
                    "remaining_cpu": 100,
                    "remaining_memory_mb": 100000,
                }
            return {"ok": True}

        runtime.call = call
        users = []

        async def native(request):
            if request.url.path == "/session":
                import json

                user = json.loads(request.content)["_cloud"]
                users.append(user)
                return httpx.Response(200, json={"id": "ses_" + str(len(users))})
            if request.url.path.endswith("/message"):
                return httpx.Response(
                    200,
                    json={
                        "info": {"tokens": {"input": 2, "output": 3}},
                        "parts": [{"type": "text", "text": "LOAD-TEST-OK"}],
                    },
                )
            return httpx.Response(200, json={})

        load.api_factory = lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(native), base_url="http://sandbox"
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app),
            base_url="http://operations",
            headers={"Authorization": "Bearer token"},
        ) as client:
            response = await client.post(
                "/cloud/admin/load-tests",
                json={
                    "request_id": "load-request",
                    "agents": [{"agent_id": "a", "users": 2}],
                },
            )
            assert response.status_code == 202, response.text
            rid = response.json()["id"]
            await asyncio.gather(*runtime.tasks)
            report = (await client.get("/cloud/admin/load-tests/" + rid)).json()
            assert report["status"] == "completed"
            assert report["summary"]["succeeded"] == 2
            assert report["summary"]["input_tokens"] == 4
            admission = (
                await client.get("/internal/v1/admission", params=users[0])
            ).json()
            assert admission["resources"]["load_test"] == rid
            response = await client.post(
                "/cloud/admin/load-tests/" + rid + "/cleanup",
                json={"confirmation": rid},
            )
            assert response.status_code == 202, response.text
            assert (
                await client.get("/internal/v1/admission", params=users[0])
            ).status_code == 409
            await asyncio.gather(*runtime.tasks)
            report = (await client.get("/cloud/admin/load-tests/" + rid)).json()
            assert report["cleanup_status"] == "cleaned"
            assert all(u["storage_state"] == "cleaned" for u in report["users"])
            assert (
                await client.get("/internal/v1/admission", params=users[0])
            ).status_code == 409
        await asyncio.gather(*(c.aclose() for c in runtime.clients.values()))

    asyncio.run(scenario())


def test_request_job_and_downstream_share_persisted_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", "token")
    monkeypatch.setenv("LOG_ROOT", str(tmp_path / "logs"))

    async def scenario():
        app = create_app(tmp_path / "data")
        runtime = app.state.runtime
        trace = "a" * 32
        parent = "b" * 16
        requests = []

        async def downstream(request):
            requests.append((request.url.path, request.headers.get("traceparent")))
            if request.url.path.endswith("/prepare"):
                return httpx.Response(
                    200, json={"release_id": "r", "version": 2, "configuration": {}}
                )
            if request.url.path.endswith("/status"):
                return httpx.Response(200, json={"release_id": "r", "ready": True})
            return httpx.Response(200, json={"ok": True, "version": 2})

        for name, old in list(runtime.clients.items()):
            runtime.clients[name] = httpx.AsyncClient(
                base_url=old.base_url,
                headers=old.headers,
                event_hooks=old.event_hooks,
                transport=httpx.MockTransport(downstream),
            )
            await old.aclose()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app),
            base_url="http://operations",
            headers={
                "Authorization": "Bearer token",
                "traceparent": f"00-{trace}-{parent}-01",
                "x-cloud-request-id": "original-request",
            },
        ) as client:
            result = await client.post(
                "/cloud/admin/models/apply", json={"request_id": "trace-job"}
            )
            assert result.status_code == 200, result.text
            jid = result.json()["job_id"]
            await asyncio.gather(*runtime.tasks)
            job = app.state.store.get(jid)
            assert job["trace_id"] == trace and job["request_span_id"] != parent
            assert requests and all(
                value.split("-")[1] == trace for _, value in requests
            )
            assert all(
                value.split("-")[2] != job["request_span_id"] for _, value in requests
            )
            import json

            events = [
                json.loads(line)
                for path in (tmp_path / "logs").rglob("events.jsonl")
                for line in path.read_text().splitlines()
            ]
            checkpoints = [
                e
                for e in events
                if e.get("job_id") == jid and e["action"].startswith("job_checkpoint.")
            ]
            assert checkpoints and all(e["trace_id"] == trace for e in checkpoints)
        await asyncio.gather(*(c.aclose() for c in runtime.clients.values()))

    asyncio.run(scenario())


def test_partial_deletion_retry_requires_fresh_preview_and_new_execution_identity(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SERVICE_TOKEN", "token")

    async def scenario():
        app = create_app(tmp_path)
        runtime = app.state.runtime
        failed = False
        execution = []

        async def call(service, path, payload=None, method=None):
            nonlocal failed
            if path.endswith("/deletion-impact"):
                if service == "catalog_service":
                    return {
                        "agent_id": "a",
                        "revision": 1,
                        "lifecycle": "archived",
                        "private_resources": [],
                        "fingerprint": "cat",
                    }
                if service == "sandbox_manager":
                    return {"sandboxes": [], "sessions": 0, "fingerprint": "sandbox"}
                return {
                    "files": 0 if failed else 2,
                    "bytes": 0 if failed else 10,
                    "fingerprint": "empty" if failed else "files",
                }
            if (
                service == "sandbox_manager"
                and payload
                and payload.get("action") == "delete"
            ):
                execution.append(payload["request_id"])
            if service == "file_service" and path.endswith("/cleanup") and not failed:
                failed = True
                raise HTTPException(503, "Lost cleanup response")
            return {"ok": True}

        runtime.call = call
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app),
            base_url="http://operations",
            headers={"Authorization": "Bearer token"},
        ) as client:
            preview = (await client.get("/cloud/admin/agents/a/delete-preview")).json()
            original = {
                "request_id": "original-delete",
                "confirmation": "a",
                "preview_id": preview["preview_id"],
            }
            jid = (
                await client.post("/cloud/admin/agents/a/delete", json=original)
            ).json()["job_id"]
            await asyncio.gather(*runtime.tasks)
            assert app.state.store.get(jid)["status"] == "needs_recovery"
            retry = {
                "request_id": "retry-delete",
                "confirmation": "a",
                "preview_id": preview["preview_id"],
            }
            assert (
                await client.post("/cloud/admin/jobs/" + jid + "/retry", json=retry)
            ).status_code == 409
            retry["preview_id"] = (
                await client.get("/cloud/admin/agents/a/delete-preview")
            ).json()["preview_id"]
            assert (
                await client.post("/cloud/admin/jobs/" + jid + "/retry", json=retry)
            ).status_code == 200
            await asyncio.gather(*runtime.tasks)
            assert app.state.store.get(jid)["status"] == "succeeded"
            assert len(execution) == 2 and execution[0] != execution[1]
            assert (
                await client.post("/cloud/admin/jobs/" + jid + "/retry", json=retry)
            ).json() == {"job_id": jid}
            assert (
                await client.post("/cloud/admin/agents/a/delete", json=original)
            ).json() == {"job_id": jid}
        await asyncio.gather(*(c.aclose() for c in runtime.clients.values()))

    asyncio.run(scenario())
