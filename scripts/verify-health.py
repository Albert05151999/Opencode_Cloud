#!/usr/bin/env python3
"""Verify health thresholds, active leases and idle restart with real Docker."""
import asyncio
import json
import shutil
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.config import load_config
from app.main import build_app

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/health/report.json"
INSTANCE = "stage21-verification"


async def verify():
    with tempfile.TemporaryDirectory(prefix="cloud-stage21-") as temporary:
        directory = Path(temporary)
        shutil.copytree(ROOT / "agents", directory / "agents")
        config = load_config(ROOT / "config.cfg")
        config = replace(config, platform=replace(config.platform, data_root=str(directory), instance_id=INSTANCE), storage=replace(config.storage, workspace_root=str(directory / "workspaces"), state_root=str(directory / "state")))
        app = build_app(config, directory / "agents")
        backend = app.state.backend
        monitor = app.state.health_monitor
        report = {"result": "running"}
        async def healthy_gateway(request):
            if request.url.path == "/session/status":
                return httpx.Response(200, json={})
            return httpx.Response(200, json="I'm alive!")
        # Dependency error injection uses a local transport; sandbox probes remain real.
        injected_client = httpx.AsyncClient(transport=httpx.MockTransport(healthy_gateway))
        original_client = monitor.client
        try:
            monitor.client = injected_client
            ready = await monitor.readiness()
            assert all(ready.values()), ready
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://controller.test") as api:
                assert (await api.get("/cloud/health/ready")).status_code == 200
                created = await api.post("/session", json={"_cloud": {"agent_id": "agent-code", "username": "alice"}})
                assert created.is_success, created.text
                assert not backend.in_use, backend.in_use
            endpoint = await backend.acquire("agent-code", "alice")
            bob = await backend.acquire("agent-code", "bob")
            path = directory / "workspaces/agent-code/alice/shared/persistent.txt"
            path.write_text("survives idle stop")
            future = datetime.now(timezone.utc) + timedelta(hours=1)
            await monitor.tick(now=future)
            assert (await backend.inspect("agent-code", "alice")) is not None
            assert backend.registry.get_sandbox("agent-code", "alice").status == "ready"
            await backend.release(endpoint)

            real_probe = backend._health_probe
            async def failed_probe(url, timeout):
                raise httpx.ConnectError("injected transient probe failure")
            backend._health_probe = failed_probe
            for _ in range(config.sandbox.health_failure_threshold - 1):
                await monitor.tick()
            assert backend.registry.get_sandbox("agent-code", "alice").status == "ready"
            await monitor.tick()
            assert backend.registry.get_sandbox("agent-code", "alice").status == "unhealthy"
            container = backend.client.containers.get(endpoint.container_id)
            assert container.status == "running"
            backend._health_probe = real_probe
            await monitor.tick()
            assert backend.registry.get_sandbox("agent-code", "alice").status == "ready"

            # Use the real /session/status endpoint for the idle-stop decision.
            monitor.client = original_client
            await monitor.tick(now=future)
            assert backend.registry.get_sandbox("agent-code", "alice").status == "stopped"
            assert await backend._get_container(endpoint.container_id) is None
            assert (await backend.inspect("agent-code", "bob")).container_id == bob.container_id
            restarted = await backend.acquire("agent-code", "alice")
            assert not restarted.reused and restarted.container_id != endpoint.container_id
            assert path.read_text() == "survives idle stop"
            async with httpx.AsyncClient(trust_env=False) as native:
                restored = await native.get(restarted.base_url + '/session/' + created.json()['id'])
                assert restored.is_success and restored.json()['id'] == created.json()['id']
            health = await real_probe(restarted.base_url + "/global/health", 2)
            assert health == {"healthy": True, "version": config.opencode.expected_version}
            await backend.release(restarted)
            await backend.release(bob)
            bob_container = backend.client.containers.get(bob.container_id)
            await asyncio.to_thread(bob_container.stop, timeout=10)
            await monitor.tick(now=future)
            assert await backend._get_container(bob.container_id) is None
            async def unavailable_gateway(request):
                raise httpx.ConnectError("injected gateway outage")
            await injected_client.aclose()
            injected_client = httpx.AsyncClient(transport=httpx.MockTransport(unavailable_gateway))
            monitor.client = injected_client
            ready_down = await monitor.readiness()
            assert ready_down["model_gateway"] is False
            assert app.state.metrics.registry.get_sample_value("model_gateway_healthy") == 0
            report = {"result": "passed", "checks": ["HTTP request releases its active lease", "active lease prevents idle removal", "transient health failures preserve ready status", "threshold failures mark unhealthy without destroying container", "successful probe restores ready", "idle removal uses real native session status", "old container removed and new container preserves workspace", "restart validates OpenCode health and version", "readiness and metrics reflect injected model gateway outage"], "health_failure_threshold": config.sandbox.health_failure_threshold, "restart_health": health, "container_id": restarted.container_id}
        except Exception as exc:
            report = {"result": "failed", "error": str(exc)}
            raise
        finally:
            REPORT.parent.mkdir(parents=True, exist_ok=True)
            REPORT.write_text(json.dumps(report, indent=2) + "\n")
            for container in backend.client.containers.list(all=True, filters={"label": f"cloud.platform_instance={INSTANCE}"}):
                if container.labels.get("cloud.platform_instance") != INSTANCE:
                    raise RuntimeError("container ownership mismatch")
                container.remove(force=True)
            await injected_client.aclose()
            await original_client.aclose()
            backend.client.close()
        return report


if __name__ == "__main__":
    print(json.dumps(asyncio.run(verify()), indent=2))
