from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from docker.errors import ImageNotFound, NotFound

from app.config import (
    AppConfig,
    AuthConfig,
    MetricsConfig,
    ModelGatewayConfig,
    OpenCodeConfig,
    PerformanceConfig,
    PlatformConfig,
    SandboxConfig,
    StorageConfig,
)
from app.registry import Registry
from app.sandbox import (
    LocalDockerBackend,
    SandboxError,
    SandboxNotReadyError,
    SandboxOwnershipError,
    sandbox_key,
)
from app.workspace import WorkspaceManager


class FakeContainer:
    def __init__(
        self,
        container_id: str,
        name: str,
        labels: dict[str, str],
        internal_port: int,
        host_port: int,
        *,
        status: str = "created",
    ) -> None:
        self.id = container_id
        self.name = name
        self.status = status
        self.start_calls = 0
        self.remove_calls: list[bool] = []
        self.attrs = {
            "Config": {"Labels": labels},
            "NetworkSettings": {
                "Ports": {
                    f"{internal_port}/tcp": [
                        {"HostIp": "127.0.0.1", "HostPort": str(host_port)}
                    ]
                }
            },
        }

    def start(self) -> None:
        self.start_calls += 1
        self.status = "running"

    def reload(self) -> None:
        pass

    def remove(self, *, force: bool) -> None:
        self.remove_calls.append(force)
        self.status = "removed"


class FakeContainers:
    def __init__(self) -> None:
        self.by_identifier: dict[str, FakeContainer] = {}
        self.create_calls: list[dict[str, Any]] = []

    def get(self, identifier: str) -> FakeContainer:
        try:
            return self.by_identifier[identifier]
        except KeyError as exc:
            raise NotFound("missing") from exc

    def list(self, *, all=False, filters=None):
        unique = {c.id: c for c in self.by_identifier.values()}
        label = (filters or {}).get("label")
        if label:
            key, value = label.split("=", 1)
            return [c for c in unique.values() if c.attrs["Config"]["Labels"].get(key) == value]
        return list(unique.values())

    def create(self, **kwargs: Any) -> FakeContainer:
        self.create_calls.append(kwargs)
        index = len(self.create_calls)
        port = int(next(iter(kwargs["ports"])).split("/")[0])
        container = FakeContainer(
            f"container-{index}",
            kwargs["name"],
            kwargs["labels"],
            port,
            41000 + index,
        )
        self.by_identifier[container.id] = container
        self.by_identifier[container.name] = container
        container.attrs["Image"] = kwargs["image"]
        container.attrs["Mounts"] = [{"Type": "bind", "Source": path, "Destination": mount["bind"], "RW": mount["mode"] == "rw"}
                                    for path, mount in kwargs["volumes"].items()]
        return container

    def add(self, container: FakeContainer) -> None:
        self.by_identifier[container.id] = container
        self.by_identifier[container.name] = container


class FakeImages:
    def __init__(self, *, present: bool = True) -> None:
        self.present = present
        self.get_calls: list[str] = []

    def get(self, image: str) -> object:
        self.get_calls.append(image)
        if not self.present:
            raise ImageNotFound("missing image")
        return SimpleNamespace(id=image)


class FakeDockerClient:
    def __init__(self, *, image_present: bool = True) -> None:
        self.containers = FakeContainers()
        self.images = FakeImages(present=image_present)


def make_config(tmp_path: Path, *, timeout: float = 1) -> AppConfig:
    return AppConfig(
        PlatformConfig("test-instance", "127.0.0.1", 8080, "INFO", "/srv/cloud"),
        AuthConfig(False, "Authorization", "HS256", "test", "/cloud/auth/token"),
        SandboxConfig(
            "runc",
            "cloud-agent-runtime:test",
            4096,
            900,
            timeout,  # type: ignore[arg-type]
            2,
            True,
            64,
            1.5,
            768,
            256,
        ),
        StorageConfig(
            str(tmp_path / "workspaces"),
            str(tmp_path / "state"),
            100,
            5,
        ),
        OpenCodeConfig("1.2.3", "/global/health", "/doc", "/event", True, True, True, True, True),
        ModelGatewayConfig("http://127.0.0.1:4001", "http://127.0.0.1:4001/health/liveliness", "usage-based-routing", 30),
        MetricsConfig(True, "/metrics", 9090, 3000),
        PerformanceConfig(100, 500, 5000, 300),
    )


@pytest.fixture
def backend_factory(tmp_path: Path):
    made: list[tuple[LocalDockerBackend, Registry, FakeDockerClient, Path]] = []

    def factory(
        *,
        client: FakeDockerClient | None = None,
        probe: Any | None = None,
        timeout: float = 1,
    ) -> tuple[LocalDockerBackend, Registry, FakeDockerClient, Path]:
        agents = tmp_path / f"agents-{len(made)}"
        for agent_id in ("agent-code", "agent-data"):
            path = agents / agent_id
            path.mkdir(parents=True)
            model = "coding-fast" if agent_id == "agent-code" else "data-fast"
            (path / "agent.cfg").write_text(
                f"""[agent]\nid = {agent_id}\ndisplay_name = Test\nimage = cloud-agent-runtime:test\nidle_timeout_seconds = 900\n\n[resources]\ncpu_limit = 1.5\nmemory_mb = 768\npids_limit = 256\n\n[models]\ndefault = {model}\nallowed = {model}\n""",
                encoding="utf-8",
            )
            (path / "opencode.json").write_text(
                json.dumps({
                    "share": "disabled", "autoupdate": False, "plugin": [],
                    "model": f"cloud-model-gateway/{model}",
                    "instructions": ["/opt/agent/AGENTS.md"],
                    "enabled_providers": ["cloud-model-gateway"],
                    "provider": {"cloud-model-gateway": {
                        "npm": "@ai-sdk/openai-compatible",
                        "options": {"baseURL": "http://host.docker.internal:4001/v1"},
                        "models": {model: {}},
                    }},
                }),
                encoding="utf-8",
            )
            (path / "AGENTS.md").write_text("test instructions\n", encoding="utf-8")
        config = make_config(tmp_path / f"data-{len(made)}", timeout=timeout)
        registry = Registry(tmp_path / f"registry-{len(made)}.db")
        registry.initialize()
        docker_client = client or FakeDockerClient()

        async def healthy(_url: str, _timeout: float) -> dict[str, Any]:
            return {"healthy": True, "version": config.opencode.expected_version}

        backend = LocalDockerBackend(
            config,
            registry,
            WorkspaceManager(config.storage.workspace_root, config.storage.state_root),
            agents,
            client=docker_client,
            health_probe=probe or healthy,
        )
        made.append((backend, registry, docker_client, agents))
        return made[-1]

    return factory


def run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def owned_labels(backend: LocalDockerBackend, agent: str, user: str) -> dict[str, str]:
    return {
        "cloud.agent_id": agent,
        "cloud.username": user,
        "cloud.platform_instance": backend.config.platform.instance_id,
        "cloud.image_version": backend.config.sandbox.image,
    }


def register_agent(backend: LocalDockerBackend, registry: Registry, agent: str) -> None:
    registry.upsert_agent(
        agent,
        str(backend.agents_root / agent),
        backend.config.sandbox.image,
        True,
    )


def test_reuse_preserves_record_until_release_updates_idle_clock(backend_factory):
    backend, registry, _, _ = backend_factory()

    async def scenario():
        first = await backend.acquire('agent-code', 'alice')
        await backend.release(first)
        before = registry.get_sandbox('agent-code', 'alice')
        second = await backend.acquire('agent-code', 'alice')
        assert registry.get_sandbox('agent-code', 'alice') == before
        assert backend.in_use[second.sandbox_id] == 1
        await backend.release(second)
        after = registry.get_sandbox('agent-code', 'alice')
        assert after.last_active_at > before.last_active_at
        assert not backend.in_use

    run(scenario())


def test_release_keeps_lease_during_write_and_drops_it_on_failure(backend_factory, monkeypatch):
    backend, registry, _, _ = backend_factory()

    async def scenario():
        endpoint = await backend.acquire('agent-code', 'alice')

        def failed_touch(sandbox_id):
            assert backend.in_use[sandbox_id] == 1
            raise OSError('test storage failure')

        monkeypatch.setattr(registry, 'touch_sandbox', failed_touch)
        with pytest.raises(OSError, match='test storage failure'):
            await backend.release(endpoint)
        assert not backend.in_use

    run(scenario())


def test_only_final_concurrent_lease_updates_idle_time(backend_factory, monkeypatch):
    backend, registry, _, _ = backend_factory()

    async def scenario():
        first = await backend.acquire('agent-code', 'alice')
        second = await backend.acquire('agent-code', 'alice')
        touches = []
        original = registry.touch_sandbox

        def touch(sandbox_id):
            touches.append(sandbox_id)
            original(sandbox_id)

        monkeypatch.setattr(registry, 'touch_sandbox', touch)
        await backend.release(first)
        assert touches == [] and backend.in_use[first.sandbox_id] == 1
        await backend.release(second)
        assert touches == [first.sandbox_id] and not backend.in_use

    run(scenario())


def test_sandbox_key_is_stable_opaque_and_identity_specific() -> None:
    assert sandbox_key("agent-code", "alice") == sandbox_key("agent-code", "alice")
    assert len(sandbox_key("agent-code", "alice")) == 20
    assert sandbox_key("agent-code", "alice") != sandbox_key("agent-code", "bob")
    assert sandbox_key("agent-code", "alice") != sandbox_key("agent-data", "alice")


def test_first_acquire_creates_starts_and_persists(backend_factory: Any) -> None:
    backend, registry, client, _ = backend_factory()
    endpoint = run(backend.acquire("agent-code", "alice"))

    assert endpoint.reused is False
    assert endpoint.base_url == "http://127.0.0.1:41001"
    assert len(client.containers.create_calls) == 1
    assert client.containers.get(endpoint.container_id).start_calls == 1
    record = registry.get_sandbox("agent-code", "alice")
    assert record is not None
    assert (record.sandbox_id, record.container_id, record.host_port, record.status) == (
        endpoint.sandbox_id,
        endpoint.container_id,
        41001,
        "ready",
    )


def test_repeat_and_five_concurrent_acquires_create_once(backend_factory: Any) -> None:
    backend, _, client, _ = backend_factory()

    async def acquire_all() -> list[Any]:
        return await asyncio.gather(
            *(backend.acquire("agent-code", "alice") for _ in range(5))
        )

    endpoints = run(acquire_all())
    repeated = run(backend.acquire("agent-code", "alice"))
    assert len(client.containers.create_calls) == 1
    assert len({item.container_id for item in endpoints + [repeated]}) == 1
    assert endpoints[0].reused is False
    assert all(item.reused for item in endpoints[1:] + [repeated])
    assert not backend._locks


def test_cold_probe_uses_short_slice_without_changing_warm_probe(backend_factory):
    backend, _, _, _ = backend_factory()
    backend.config = replace(backend.config, sandbox=replace(backend.config.sandbox, start_timeout_seconds=10))
    original = backend._health_probe
    limits = []
    async def probe(url, timeout):
        limits.append(timeout)
        return await original(url, timeout)
    backend._health_probe = probe
    run(backend.acquire('agent-code', 'alice'))
    assert limits and max(limits) <= 0.25
    limits.clear()
    run(backend.acquire('agent-code', 'alice'))
    assert limits == [2.0]


def test_different_users_and_agents_have_isolated_mounts(backend_factory: Any) -> None:
    backend, _, client, agents = backend_factory()
    run(backend.acquire("agent-code", "alice"))
    run(backend.acquire("agent-code", "bob"))
    run(backend.acquire("agent-data", "alice"))

    calls = client.containers.create_calls
    assert len(calls) == 3
    mounts = [call["volumes"] for call in calls]
    workspace_sources = [
        next(source for source, target in volume.items() if target["bind"] == "/workspace")
        for volume in mounts
    ]
    assert len(set(workspace_sources)) == 3
    assert str(agents / "agent-code") in mounts[0]
    assert str(agents / "agent-code") in mounts[1]
    assert str(agents / "agent-data") in mounts[2]


def test_stopped_owned_container_is_started_without_create(backend_factory: Any) -> None:
    backend, registry, client, _ = backend_factory()
    key = sandbox_key("agent-code", "alice")
    container = FakeContainer(
        "existing", f"cloud-agent-{key}", owned_labels(backend, "agent-code", "alice"),
        4096, 42000, status="exited",
    )
    client.containers.add(container)
    register_agent(backend, registry, "agent-code")
    registry.upsert_sandbox(
        sandbox_id=f"sbx_{key}", agent_id="agent-code", username="alice",
        container_id=container.id, host_port=42000, status="stopped",
        image_version=backend.config.sandbox.image,
    )

    endpoint = run(backend.acquire("agent-code", "alice"))
    assert endpoint.reused is True
    assert container.start_calls == 1
    assert client.containers.create_calls == []


def test_missing_recorded_container_is_rebuilt(backend_factory: Any) -> None:
    backend, registry, client, _ = backend_factory()
    key = sandbox_key("agent-code", "alice")
    register_agent(backend, registry, "agent-code")
    registry.upsert_sandbox(
        sandbox_id=f"sbx_{key}", agent_id="agent-code", username="alice",
        container_id="vanished", host_port=42000, status="ready",
        image_version=backend.config.sandbox.image,
    )

    endpoint = run(backend.acquire("agent-code", "alice"))
    assert endpoint.reused is False
    assert len(client.containers.create_calls) == 1
    assert registry.get_sandbox("agent-code", "alice").container_id == endpoint.container_id


def test_label_mismatch_is_rejected(backend_factory: Any) -> None:
    backend, _, client, _ = backend_factory()
    key = sandbox_key("agent-code", "alice")
    labels = owned_labels(backend, "agent-code", "alice")
    labels["cloud.username"] = "bob"
    client.containers.add(
        FakeContainer("wrong-owner", f"cloud-agent-{key}", labels, 4096, 42000, status="running")
    )

    with pytest.raises(SandboxOwnershipError, match="label mismatch"):
        run(backend.acquire("agent-code", "alice"))
    assert client.containers.create_calls == []


def test_health_version_mismatch_fails_and_removes_container(backend_factory: Any) -> None:
    async def wrong_version(_url: str, _timeout: float) -> dict[str, Any]:
        return {"healthy": True, "version": "wrong"}

    backend, registry, client, _ = backend_factory(probe=wrong_version, timeout=0.01)
    with pytest.raises(SandboxNotReadyError, match="health payload mismatch"):
        run(backend.acquire("agent-code", "alice"))

    created = next(iter({c.id: c for c in client.containers.by_identifier.values()}.values()))
    assert created.remove_calls == [True]
    record = registry.get_sandbox("agent-code", "alice")
    assert record is not None
    assert (record.status, record.container_id, record.host_port) == ("failed", None, None)


def test_create_uses_hardened_resources_mounts_and_networking(backend_factory: Any) -> None:
    backend, _, client, agents = backend_factory()
    # Distinct platform values ensure Agent overrides actually reach Docker.
    backend.config = replace(backend.config, sandbox=replace(
        backend.config.sandbox, default_cpu=8, default_memory_mb=8192, default_pids=1024,
    ))
    run(backend.acquire("agent-code", "alice"))
    kwargs = client.containers.create_calls[0]

    assert kwargs["read_only"] is True
    assert kwargs["tmpfs"] == {"/tmp": "rw,nosuid,nodev,size=64m"}
    assert kwargs["nano_cpus"] == 1_500_000_000
    assert kwargs["mem_limit"] == "768m"
    assert kwargs["pids_limit"] == 256
    assert kwargs["runtime"] == "runc"
    assert kwargs["privileged"] is False
    assert kwargs["init"] is True
    assert kwargs["ports"] == {"4096/tcp": ("127.0.0.1", None)}
    assert kwargs["extra_hosts"] == {"host.docker.internal": "host-gateway"}
    assert kwargs["environment"] == {
        "XDG_CONFIG_HOME": "/opt/agent/global",
        "OPENCODE_DISABLE_AUTOUPDATE": "1",
        "OPENCODE_DISABLE_MODELS_FETCH": "1",
        "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
        "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",
    }
    volumes = kwargs["volumes"]
    assert len(volumes) == 3
    assert {entry["bind"] for entry in volumes.values()} == {
        "/workspace", "/state/opencode", "/opt/agent"
    }
    assert volumes[str(agents / "agent-code")] == {"bind": "/opt/agent", "mode": "ro"}
    assert sorted(entry["mode"] for entry in volumes.values()) == ["ro", "rw", "rw"]


def test_missing_image_fails_without_create_and_persists_failure(
    backend_factory: Any,
) -> None:
    backend, registry, client, _ = backend_factory(client=FakeDockerClient(image_present=False))

    with pytest.raises(SandboxError, match="not present"):
        run(backend.acquire("agent-code", "alice"))

    assert client.containers.create_calls == []
    record = registry.get_sandbox("agent-code", "alice")
    assert record is not None
    assert (record.status, record.container_id) == ("failed", None)


def test_recovery_repairs_stale_docker_route_preserves_sessions_and_marks_missing(backend_factory):
    backend, registry, client, _ = backend_factory()
    async def scenario():
        first = await backend.acquire("agent-code", "alice")
        second = await backend.acquire("agent-code", "bob")
        await backend.release(first)
        await backend.release(second)
        registry.record_session("ses_recovery", first.sandbox_id, "agent-code", "alice", "sessions/custom")
        original = registry.get_sandbox("agent-code", "alice")
        registry.upsert_sandbox(sandbox_id=first.sandbox_id, agent_id="agent-code", username="alice",
            container_id="stale", host_port=1, status="unhealthy", image_version=original.image_version,
            last_active_at=original.last_active_at)
        client.containers.by_identifier = {k:v for k,v in client.containers.by_identifier.items() if v.id != second.container_id}
        assert await backend.reconcile() == {"observed": 1, "missing": 1}
        recovered = registry.get_sandbox("agent-code", "alice")
        assert recovered.container_id == first.container_id and recovered.host_port == first.host_port
        assert recovered.status == "ready" and recovered.last_active_at == original.last_active_at
        assert registry.get_session_route("ses_recovery").workspace_relpath == "sessions/custom"
        assert registry.get_sandbox("agent-code", "bob").status == "missing"
        assert await backend.reconcile() == {"observed": 1, "missing": 1}
    run(scenario())


def test_recovery_rejects_wrong_mount_before_registry_rewrite(backend_factory):
    backend, registry, client, _ = backend_factory()
    endpoint = run(backend.acquire("agent-code", "alice"))
    original = registry.get_sandbox("agent-code", "alice")
    container = client.containers.get(endpoint.container_id)
    container.attrs["Mounts"][0]["Source"] = "/another-user/workspace"
    with pytest.raises(SandboxOwnershipError, match="mount ownership"):
        run(backend.reconcile())
    assert registry.get_sandbox("agent-code", "alice") == original
