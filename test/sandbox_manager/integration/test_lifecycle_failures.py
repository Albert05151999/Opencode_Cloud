import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from sandbox_manager.backend import SandboxEndpoint
from sandbox_manager.registry import Registry
from test.sandbox_manager.integration.support import (
    disable_health_monitor,
    patch_http_clients,
    service_config,
)
from test.sandbox_manager.integration.test_remote_catalog import full_bundle


@pytest.fixture
def environment(tmp_path, monkeypatch):
    import sandbox_manager.main as service

    control = {
        "bundle": full_bundle(1),
        "deny_resources": False,
        "unknown_runtime": False,
    }
    resource_checks = []

    def handle(request):
        if request.url.path.endswith("/bundle"):
            return httpx.Response(200, json=control["bundle"])
        if request.url.path == "/internal/v1/admission":
            resource_checks.append(dict(request.url.params))
            return httpx.Response(
                409 if control["deny_resources"] else 200,
                json={"resources": None, "detail": "admission denied"},
            )
        if request.url.path.endswith("/desired-state"):
            return httpx.Response(
                200, json={"state": control.get("desired_state", "running")}
            )
        if request.url.path == "/session/status":
            return httpx.Response(503 if control["unknown_runtime"] else 200, json=control.get("runtime_status", {}))
        return httpx.Response(200, json={})

    patch_http_clients(monkeypatch, handle)
    disable_health_monitor(monkeypatch, service)
    config = service_config(tmp_path)
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    registry.upsert_agent("agent-code", str(tmp_path / "agent-code"), "runtime")
    registry.upsert_sandbox(
        sandbox_id="sbx_a",
        agent_id="agent-code",
        username="alice",
        container_id="container-0",
        host_port=4000,
        status="ready",
        image_version="runtime",
    )

    class Container:
        def __init__(self, cid, status="running"):
            self.id, self.status = cid, status

        def reload(self):
            pass

        def stop(self, timeout=10):
            self.status = "exited"

    class Backend:
        def __init__(self):
            self.registry = registry
            self.in_use = {}
            self._locks = {}
            self.removed = []
            self.created = 0
            self.client = SimpleNamespace(ping=lambda: True, close=lambda: None)
            self.containers = {"container-0": Container("container-0")}
            self.fail_acquire = False

        async def inspect(self, aid, username):
            record = registry.get_sandbox(aid, username)
            container = self.containers.get(record.container_id)
            if not container or container.status != "running":
                return None
            return SandboxEndpoint(
                record.sandbox_id, container.id, 4000, "http://runtime.test", False
            )

        async def _get_container(self, cid):
            return self.containers.get(cid)

        async def _find_existing(self, record, key, aid, username):
            return self.containers.get(record.container_id)

        def _verify_ownership(self, container, aid, username):
            pass

        async def _remove_owned(self, container):
            self.removed.append(container.id)
            self.containers.pop(container.id, None)

        async def _acquire_locked(self, aid, username):
            # The actual backend checks resource policy while creating. The
            # coordinator's own local admission block must not reject this path.
            await asyncio.to_thread(self.management.resources_for, aid, username)
            if self.fail_acquire:
                raise RuntimeError("Simulated interrupted restart")
            self.created += 1
            cid = f"container-{self.created}"
            self.containers[cid] = Container(cid)
            definition = self.agent_catalog.load(aid)
            registry.upsert_agent(aid, str(definition.path), "runtime")
            registry.upsert_sandbox(
                sandbox_id="sbx_a",
                agent_id=aid,
                username=username,
                container_id=cid,
                host_port=4000,
                status="ready",
                image_version="runtime",
            )
            return await self.inspect(aid, username)

    backend = Backend()
    app = service.create_app(config, backend)
    with TestClient(
        app, headers={"Authorization": "Bearer service"}, raise_server_exceptions=False
    ) as client:
        yield SimpleNamespace(
            client=client,
            backend=backend,
            control=control,
            config=config,
            service=service,
            checks=resource_checks,
        )


def test_restart_is_durable_idempotent_and_rejects_changed_identity(environment):
    e = environment
    body = {"action": "restart", "request_id": "restart-request"}
    first = e.client.post("/internal/v1/sandboxes/sbx_a/actions", json=body)
    assert first.status_code == 200, first.text
    assert e.backend.created == 1 and len(e.backend.removed) == 1
    assert (
        e.client.post("/internal/v1/sandboxes/sbx_a/actions", json=body).json()
        == first.json()
    )
    assert e.backend.created == 1
    assert (
        e.client.post(
            "/internal/v1/sandboxes/sbx_a/actions", json={**body, "action": "stop"}
        ).status_code
        == 409
    )
    # A separate app instance reads the persistent journal before any Docker or
    # policy call, proving response-loss/restart does not repeat the operation.
    second = e.service.create_app(e.config, e.backend)
    with TestClient(second, headers={"Authorization": "Bearer service"}) as client:
        assert (
            client.post("/internal/v1/sandboxes/sbx_a/actions", json=body).json()
            == first.json()
        )
    assert e.backend.created == 1


def test_interrupted_restart_is_never_blindly_replayed(environment):
    e = environment
    e.backend.fail_acquire = True
    body = {"action": "restart", "request_id": "interrupted-restart"}
    assert (
        e.client.post("/internal/v1/sandboxes/sbx_a/actions", json=body).status_code
        == 500
    )
    assert len(e.backend.removed) == 1
    e.backend.fail_acquire = False
    assert (
        e.client.post("/internal/v1/sandboxes/sbx_a/actions", json=body).status_code
        == 409
    )
    assert e.backend.created == 0 and len(e.backend.removed) == 1


@pytest.mark.parametrize("state", ["exited", "absent"])
def test_stopped_or_absent_owned_process_does_not_block_global_publish(
    environment, state
):
    e = environment
    if state == "absent":
        e.backend.containers.clear()
    else:
        e.backend.containers["container-0"].status = state
    result = e.client.post(
        "/internal/v1/agents/*/actions",
        json={"action": "quiesce", "request_id": "global-quiesce", "timeout": 0},
    )
    assert result.status_code == 200, result.text
    assert e.client.get("/internal/v1/sandboxes/sbx_a").json()["execution"] == "idle"


def test_running_unknown_or_active_lease_blocks_quiesce(environment):
    e = environment
    e.control["unknown_runtime"] = True
    assert (
        e.client.post(
            "/internal/v1/agents/*/actions",
            json={"action": "quiesce", "request_id": "unknown", "timeout": 0},
        ).status_code
        == 409
    )
    e.backend.containers.clear()
    e.backend.in_use["sbx_a"] = 1
    assert (
        e.client.post(
            "/internal/v1/agents/*/actions",
            json={"action": "quiesce", "request_id": "leased", "timeout": 0},
        ).status_code
        == 409
    )


def test_recovery_preflights_resources_before_removing_container(environment):
    e = environment
    e.control["deny_resources"] = True
    result = e.client.post(
        "/internal/v1/sandboxes/sbx_a/actions",
        json={"action": "recover", "request_id": "recovery-denied"},
    )
    assert result.status_code == 409 and not e.backend.removed
    e.control["deny_resources"] = False
    assert (
        e.client.post(
            "/internal/v1/sandboxes/sbx_a/actions",
            json={"action": "recover", "request_id": "recovery-allowed"},
        ).status_code
        == 200
    )
    assert e.backend.created == 1 and len(e.checks) >= 2


def test_staged_verification_and_application_status_are_durable(environment):
    e = environment
    path = "/internal/v1/agents/agent-code"
    assert (
        e.client.post(
            path + "/actions",
            json={
                "action": "apply",
                "request_id": "apply-two",
                "bundle": full_bundle(2),
            },
        ).status_code
        == 200
    )
    status = e.client.get(path + "/application-status").json()
    assert status == {
        "version": "2",
        "staged": True,
        "verified": False,
        "blocked": True,
    }
    assert (
        e.client.post(
            path + "/actions", json={"action": "verify", "request_id": "verify-two"}
        ).status_code
        == 200
    )
    assert e.backend.created == 1
    assert e.client.get(path + "/application-status").json()["verified"]
    e.control["bundle"] = full_bundle(2)
    assert (
        e.client.post(
            path + "/actions", json={"action": "resume", "request_id": "resume-two"}
        ).status_code
        == 200
    )
    assert e.client.get(path + "/application-status").json() == {
        "version": "2",
        "staged": False,
        "verified": True,
        "blocked": False,
    }
    fresh_backend = type(e.backend)()
    with TestClient(
        e.service.create_app(e.config, fresh_backend),
        headers={"Authorization": "Bearer service"},
    ) as restarted:
        restored = restarted.get(path + "/application-status")
        assert restored.status_code == 200, restored.text
        assert restored.json() == {
            "version": "2",
            "staged": False,
            "verified": True,
            "blocked": False,
        }
    assert (
        e.client.post(
            path + "/actions",
            json={
                "action": "apply",
                "request_id": "apply-three",
                "bundle": full_bundle(3),
            },
        ).status_code
        == 200
    )
    assert not e.client.get(path + "/application-status").json()["verified"]


def test_verification_preserves_manually_stopped_users(environment):
    e = environment
    e.backend.containers["container-0"].status = "exited"
    e.control["desired_state"] = "stopped"
    path = "/internal/v1/agents/agent-code"
    assert (
        e.client.post(
            path + "/actions",
            json={
                "action": "apply",
                "request_id": "stopped-apply",
                "bundle": full_bundle(2),
            },
        ).status_code
        == 200
    )
    assert (
        e.client.post(
            path + "/actions", json={"action": "verify", "request_id": "stopped-verify"}
        ).status_code
        == 200
    )
    assert e.backend.created == 0
    assert e.client.get(path + "/application-status").json()["verified"]


def test_runtime_security_reports_actual_owned_flags_without_credentials(environment):
    e = environment
    container = e.backend.containers["container-0"]
    container.attrs = {
        "HostConfig": {
            "Privileged": True,
            "ReadonlyRootfs": False,
            "NetworkMode": "host",
            "CapAdd": ["SYS_ADMIN"],
            "CapDrop": [],
            "NanoCpus": 0,
            "Memory": 0,
            "PidsLimit": -1,
        },
        "Config": {
            "Image": "runtime:test",
            "Env": ["PRIVATE_KEY=must-not-be-returned"],
        },
    }
    response = e.client.get("/internal/v1/runtime-security")
    assert response.status_code == 200
    report = response.json()
    assert report["scope"] == "managed_sandboxes"
    assert report["summary"]["with_issues"] == 1
    row = report["containers"][0]
    assert {
        "privileged",
        "read_only_rootfs",
        "host_network",
        "added_capabilities",
        "cpu_limit",
        "memory_limit_bytes",
        "pids_limit",
    } <= set(row["issues"])
    assert "must-not-be-returned" not in response.text
    container.attrs = {"HostConfig": {}}
    row = e.client.get("/internal/v1/runtime-security").json()["containers"][0]
    assert row["status"] == "unknown" and "privileged" in row["unknown_checks"]
    container.attrs = {
        "HostConfig": {
            "Privileged": False,
            "ReadonlyRootfs": True,
            "NetworkMode": "bridge",
            "CapAdd": None,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "NanoCpus": 1000000000,
            "Memory": 1024**3,
            "PidsLimit": 256,
        }
    }
    assert (
        e.client.get("/internal/v1/runtime-security").json()["containers"][0]["status"]
        == "ok"
    )

    container.attrs["HostConfig"]["SecurityOpt"] = None
    row = e.client.get("/internal/v1/runtime-security").json()["containers"][0]
    assert row["status"] == "issues" and "no_new_privileges" in row["issues"]


def test_detail_observes_stopped_without_admission(environment):
    e=environment
    e.control['deny_resources']=True
    e.backend.containers['container-0'].status='exited'
    response=e.client.get('/internal/v1/sandboxes/sbx_a')
    assert response.status_code==200
    assert response.json()['status']=='stopped'
    assert response.json()['container_state']=='exited'
    assert e.backend.registry.get_sandbox('agent-code','alice').status=='stopped'


def test_detail_foreign_observation_does_not_mark_stopped(environment):
    e=environment
    e.backend.containers['container-0'].status='exited'
    def reject(*args):raise RuntimeError('foreign')
    e.backend._verify_ownership=reject
    response=e.client.get('/internal/v1/sandboxes/sbx_a')
    assert response.json()['status']=='ready'
    assert response.json()['execution']=='unknown'


def test_detail_refreshes_after_concurrent_start_lock(environment):
    e=environment
    endpoint=next(route.endpoint for route in e.client.app.routes if getattr(route,'path',None)=='/internal/v1/sandboxes/by-owner/{agent_id}/{username}')
    async def scenario():
        lock=asyncio.Lock();e.backend._locks[('agent-code','alice')]=lock
        await lock.acquire()
        e.backend.containers['container-0'].status='exited'
        task=asyncio.create_task(endpoint('agent-code','alice'))
        await asyncio.sleep(.01)
        assert not task.done()
        # Simulate the in-flight start finishing before detail acquires its lock.
        e.backend.containers['container-0'].status='running'
        lock.release()
        result=await task
        assert result['status']=='ready' and result['container_state']=='running'
    e.client.portal.call(scenario)
def test_destroy_is_idempotent_and_next_acquire_recreates_container(environment):
    e=environment
    before=e.backend.registry.list_sessions_for_sandbox('sbx_a')
    body={"action":"destroy","request_id":"destroy-keep-data"}
    response=e.client.post('/internal/v1/sandboxes/sbx_a/actions',json=body)
    assert response.status_code == 200, response.text
    record=e.backend.registry.get_sandbox('agent-code','alice')
    assert record.container_id is None and record.status == 'destroyed'
    assert e.backend.created == 0 and e.backend.removed == ['container-0']
    assert e.backend.registry.list_sessions_for_sandbox('sbx_a') == before
    assert e.client.post('/internal/v1/sandboxes/sbx_a/actions',json=body).status_code == 200
    assert e.backend.removed == ['container-0']
    response=e.client.post('/internal/v1/sandboxes/sbx_a/actions',json={'action':'start','request_id':'after-destroy-start'})
    assert response.status_code == 200, response.text
    assert e.backend.registry.get_sandbox('agent-code','alice').container_id == 'container-1'


def test_destroy_busy_sandbox_requires_current_force_preview(environment):
    e=environment
    e.control['unknown_runtime']=True
    body={'action':'destroy','request_id':'destroy-unhealthy'}
    assert e.client.post('/internal/v1/sandboxes/sbx_a/actions',json=body).status_code == 409
    assert not e.backend.removed
    preview=e.client.get('/internal/v1/sandboxes/sbx_a/force-preview').json()
    result=e.client.post('/internal/v1/sandboxes/sbx_a/actions',json={**body,'force':True,'preview_id':preview['preview_id']})
    assert result.status_code == 200, result.text
    assert e.backend.removed == ['container-0']


def test_event_subscription_is_not_an_execution_lease(environment):
    e = environment
    e.backend.in_use['sbx_a'] = 1
    e.backend.event_subscribers = {'sbx_a': 1}
    detail = e.client.get('/internal/v1/sandboxes/sbx_a').json()
    assert detail['execution'] == 'idle'
    assert detail['event_subscriptions'] == 1 and detail['active_request_leases'] == 0
    response = e.client.post('/internal/v1/agents/agent-code/actions', json={
        'action': 'quiesce', 'request_id': 'quiesce-with-observer', 'timeout': .01,
    })
    assert response.status_code == 200, response.text
    response = e.client.post('/internal/v1/sandboxes/sbx_a/actions', json={
        'action': 'destroy', 'request_id': 'destroy-with-observer',
    })
    assert response.status_code == 200, response.text
    assert e.backend.removed == ['container-0']


def test_execution_or_unknown_status_still_blocks_with_event_subscribers(environment):
    e = environment
    e.backend.in_use['sbx_a'] = 2
    e.backend.event_subscribers = {'sbx_a': 1}
    assert e.client.get('/internal/v1/sandboxes/sbx_a').json()['execution'] == 'busy'
    assert e.client.post('/internal/v1/sandboxes/sbx_a/actions', json={
        'action': 'destroy', 'request_id': 'destroy-execution-and-observer',
    }).status_code == 409
    e.backend.in_use['sbx_a'] = 1
    e.control['runtime_status'] = {'ses_async': {'type': 'busy'}}
    assert e.client.get('/internal/v1/sandboxes/sbx_a').json()['execution'] == 'busy'
    assert e.client.post('/internal/v1/sandboxes/sbx_a/actions', json={
        'action': 'destroy', 'request_id': 'destroy-active-runtime-with-observer',
    }).status_code == 409
    e.control['unknown_runtime'] = True
    assert e.client.get('/internal/v1/sandboxes/sbx_a').json()['execution'] == 'unknown'
    assert e.client.post('/internal/v1/sandboxes/sbx_a/actions', json={
        'action': 'destroy', 'request_id': 'destroy-unknown-and-observer',
    }).status_code == 409


def test_destroy_finds_owned_orphan_when_registry_container_id_is_missing(environment):
    e = environment
    e.backend.registry.upsert_sandbox(
        sandbox_id="sbx_a", agent_id="agent-code", username="alice",
        container_id=None, host_port=None, status="error", image_version="runtime",
    )

    async def find_existing(record, key, aid, username):
        return e.backend.containers.get("container-0")

    e.backend._find_existing = find_existing
    preview = e.client.get('/internal/v1/sandboxes/sbx_a/force-preview').json()
    result = e.client.post('/internal/v1/sandboxes/sbx_a/actions', json={
        'action': 'destroy', 'request_id': 'destroy-owned-orphan',
        'force': True, 'preview_id': preview['preview_id'],
    })
    assert result.status_code == 200, result.text
    assert e.backend.removed == ['container-0']
