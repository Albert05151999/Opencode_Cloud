"""Single-host Docker sandbox lifecycle management."""

from __future__ import annotations

import asyncio
import hashlib
import ssl
import time
from weakref import WeakValueDictionary
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

import docker
import httpx
from docker.errors import APIError, DockerException, ImageNotFound, NotFound

from app.agents import AgentCatalog, AgentDefinitionError
from app.config import AppConfig
from app.metrics import PlatformMetrics
from app.registry import Registry, SandboxRecord, utc_now
from app.workspace import WorkspaceManager, WorkspacePathError, validate_identifier


_HEALTH_TLS_CONTEXT = ssl.create_default_context()


class SandboxError(RuntimeError):
    """Base class for sandbox acquisition failures."""


class SandboxOwnershipError(SandboxError):
    """Raised when a container's authoritative labels do not match its route."""


class SandboxNotReadyError(SandboxError):
    """Raised when OpenCode does not become healthy before the deadline."""


@dataclass(frozen=True)
class SandboxEndpoint:
    sandbox_id: str
    container_id: str
    host_port: int
    base_url: str
    reused: bool


HealthProbe = Callable[[str, float], Awaitable[dict[str, Any]]]


def sandbox_key(agent_id: str, username: str, *, length: int = 20) -> str:
    """Return the stable, opaque key for one Agent x User sandbox."""

    digest = hashlib.sha256(f"{agent_id}\0{username}".encode()).hexdigest()
    return digest[:length]


class LocalDockerBackend:
    """Acquire and reuse one Docker container per Agent x User key."""

    def __init__(
        self,
        config: AppConfig,
        registry: Registry,
        workspaces: WorkspaceManager,
        agents_root: str | Path,
        *,
        client: Any | None = None,
        health_probe: HealthProbe | None = None,
        metrics: PlatformMetrics | None = None,
    ) -> None:
        self.config = config
        self.metrics = metrics
        if metrics is not None:
            metrics.sandbox_active.set_function(self._active_count)
        self.registry = registry
        self.workspaces = workspaces
        self.agents_root = Path(agents_root).expanduser().absolute()
        self.agents_root.mkdir(parents=True, exist_ok=True)
        self._agents_root_real = self.agents_root.resolve(strict=True)
        self.agent_catalog = AgentCatalog(self.agents_root)
        self.client = client or docker.from_env()
        self._health_probe = health_probe or self._http_health_probe
        self._locks: WeakValueDictionary[tuple[str, str], asyncio.Lock] = WeakValueDictionary()
        self.in_use: dict[str, int] = {}

    async def reconcile(self) -> dict[str, int]:
        """Validate this instance's Docker snapshot before accepting requests."""
        containers = await asyncio.to_thread(
            self.client.containers.list, all=True,
            filters={"label": f"cloud.platform_instance={self.config.platform.instance_id}"},
        )
        observed = []
        owners = set()
        ports = set()
        expected_image = (await asyncio.to_thread(self.client.images.get, self.config.sandbox.image)).id if containers else None
        for container in containers:
            await asyncio.to_thread(container.reload)
            labels = container.attrs.get("Config", {}).get("Labels") or {}
            agent = validate_identifier(labels.get("cloud.agent_id"), "agent_id")
            username = validate_identifier(labels.get("cloud.username"), "username")
            self._verify_ownership(container, agent, username)
            key = sandbox_key(agent, username)
            if (agent, username) in owners or container.name != f"cloud-agent-{key}":
                raise SandboxOwnershipError("duplicate or incorrectly named sandbox during recovery")
            if container.attrs.get("Image") != expected_image:
                raise SandboxOwnershipError("actual sandbox image differs from recovery configuration")
            owners.add((agent, username))
            agent_path = await asyncio.to_thread(self._agent_path, agent)
            expected_mounts = {
                "/opt/agent": (agent_path, False),
                "/workspace": (self.workspaces.workspace_root.resolve(strict=True) / agent / username, True),
                "/state/opencode": (self.workspaces.state_root.resolve(strict=True) / agent / username / "opencode", True),
            }
            mounts = {m["Destination"]: m for m in container.attrs.get("Mounts", []) if m.get("Type") == "bind"}
            if set(mounts) != set(expected_mounts):
                raise SandboxOwnershipError("unexpected sandbox bind mounts during recovery")
            for destination, (expected_path, writable) in expected_mounts.items():
                mount = mounts[destination]
                # Compare lexical paths too: another user's symlink is not an acceptable substitute.
                if (Path(mount["Source"]).absolute() != expected_path.absolute()
                        or expected_path.resolve(strict=True) != expected_path.absolute()
                        or bool(mount["RW"]) != writable):
                    raise SandboxOwnershipError("sandbox mount ownership differs during recovery")
            old = await asyncio.to_thread(self.registry.get_sandbox, agent, username)
            sid = old.sandbox_id if old else f"sbx_{key}"
            port = None
            status = "stopped"
            if container.status == "running":
                endpoint = self._endpoint(sid, container, reused=True)
                port = endpoint.host_port
                if port in ports:
                    raise SandboxOwnershipError("duplicate native host port during recovery")
                ports.add(port)
                try:
                    health = await self._health_probe(endpoint.base_url + self.config.opencode.health_path, 2)
                    status = "ready" if health == {"healthy": True, "version": self.config.opencode.expected_version} else "unhealthy"
                except (httpx.HTTPError, ValueError):
                    status = "unhealthy"
            now = utc_now()
            observed.append(SandboxRecord(sid, agent, username, container.id, port, status,
                self.config.sandbox.image, old.last_active_at if old else now, old.created_at if old else now))
        # No sandbox/session writes happen until the complete Docker snapshot is validated.
        for record in observed:
            await asyncio.to_thread(self.registry.upsert_agent, record.agent_id,
                str(self.agents_root / record.agent_id), self.config.sandbox.image)
        missing = await asyncio.to_thread(self.registry.reconcile, observed)
        return {"observed": len(observed), "missing": len(missing)}

    async def acquire(self, agent_id: str, username: str) -> SandboxEndpoint:
        key = (agent_id, username)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            acquire_started = time.perf_counter()
            if self.metrics is not None:
                self.metrics.sandbox_starting.inc()
            try:
                endpoint = await self._acquire_locked(agent_id, username)
                self.in_use[endpoint.sandbox_id] = self.in_use.get(endpoint.sandbox_id, 0) + 1
                if self.metrics is not None and endpoint.reused:
                    self.metrics.sandbox_reuse.inc()
                elif self.metrics is not None:
                    self.metrics.sandbox_cold_start.observe(time.perf_counter() - acquire_started)
                return endpoint
            except Exception:
                if self.metrics is not None:
                    self.metrics.sandbox_failures.inc()
                raise
            finally:
                if self.metrics is not None:
                    self.metrics.sandbox_starting.dec()

    def _active_count(self) -> int:
        with self.registry.connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM sandboxes WHERE status='ready'").fetchone()[0]

    async def _start_container(self, container: Any) -> None:
        started = time.perf_counter()
        try:
            await asyncio.to_thread(container.start)
        finally:
            if self.metrics is not None:
                self.metrics.sandbox_start.observe(time.perf_counter() - started)

    async def inspect(self, agent_id: str, username: str) -> SandboxEndpoint | None:
        record = await asyncio.to_thread(self.registry.get_sandbox, agent_id, username)
        if record is None or not record.container_id:
            return None
        container = await self._get_container(record.container_id)
        if container is None:
            return None
        await asyncio.to_thread(container.reload)
        self._verify_ownership(container, agent_id, username)
        if container.status != "running":
            return None
        return self._endpoint(record.sandbox_id, container, reused=True)

    async def release(self, endpoint: SandboxEndpoint, *, activity_persisted: bool = False) -> None:
        """End an active request lease and update its idle clock."""
        count = self.in_use.get(endpoint.sandbox_id, 0)
        if count > 1:
            # Remaining requests already prevent eviction. Their final release
            # persists the later idle timestamp, so no intermediate write is needed.
            self.in_use[endpoint.sandbox_id] = count - 1
            return
        # Keep the lease until the idle timestamp is durable: otherwise a
        # health tick can evict between the lease decrement and this write.
        try:
            if not activity_persisted:
                await asyncio.to_thread(self.registry.touch_sandbox, endpoint.sandbox_id)
        finally:
            remaining = self.in_use.get(endpoint.sandbox_id, 0) - 1
            if remaining > 0:
                self.in_use[endpoint.sandbox_id] = remaining
            else:
                self.in_use.pop(endpoint.sandbox_id, None)

    async def _acquire_locked(self, agent_id: str, username: str) -> SandboxEndpoint:
        agent_path = await asyncio.to_thread(self._agent_path, agent_id)
        layout = await asyncio.to_thread(self.workspaces.ensure_user_layout, agent_id, username)
        key = sandbox_key(agent_id, username)
        sid = f"sbx_{key}"
        image = self.config.sandbox.image

        await asyncio.to_thread(
            self.registry.upsert_agent, agent_id, str(agent_path), image, True
        )
        record = await asyncio.to_thread(self.registry.get_sandbox, agent_id, username)
        container = await self._find_existing(record, key, agent_id, username)

        if container is not None:
            # containers.get() already returned a fresh Docker inspection.
            self._verify_ownership(container, agent_id, username)
            if container.status != "running":
                try:
                    await self._start_container(container)
                    await asyncio.to_thread(container.reload)
                except DockerException:
                    await self._remove_owned(container)
                    container = None
            if container is not None:
                try:
                    endpoint = await self._wait_ready(sid, container, reused=True)
                except SandboxNotReadyError:
                    await self._remove_owned(container)
                else:
                    if record is None or (
                        record.status, record.container_id, record.host_port, record.image_version
                    ) != ("ready", endpoint.container_id, endpoint.host_port, image):
                        await self._persist(endpoint, agent_id, username, "ready")
                    # An unchanged ready sandbox needs no write on acquire.
                    # The lease prevents idle eviction; release persists activity.
                    return endpoint

        await asyncio.to_thread(
            self.registry.upsert_sandbox,
            sandbox_id=sid,
            agent_id=agent_id,
            username=username,
            container_id=None,
            host_port=None,
            status="creating",
            image_version=image,
        )
        container = None
        try:
            create_started = time.perf_counter()
            container = await self._create_container(
                key, agent_id, username, agent_path, layout.workspace, layout.state
            )
            if self.metrics is not None:
                self.metrics.sandbox_create.observe(time.perf_counter() - create_started)
                self.metrics.sandbox_created.inc()
            await self._start_container(container)
            await asyncio.to_thread(container.reload)
            endpoint = await self._wait_ready(sid, container, reused=False)
            await self._persist(endpoint, agent_id, username, "ready")
            return endpoint
        except (DockerException, SandboxError, OSError) as exc:
            if container is not None:
                await self._remove_owned(container)
            await asyncio.to_thread(
                self.registry.upsert_sandbox,
                sandbox_id=sid,
                agent_id=agent_id,
                username=username,
                container_id=None,
                host_port=None,
                status="failed",
                image_version=image,
            )
            if isinstance(exc, SandboxError):
                raise
            raise SandboxError(f"failed to create sandbox {sid}: {exc}") from exc

    async def _find_existing(
        self,
        record: SandboxRecord | None,
        key: str,
        agent_id: str,
        username: str,
    ) -> Any | None:
        container = None
        if record is not None and record.container_id:
            container = await self._get_container(record.container_id)
        if container is None:
            container = await self._get_container(f"cloud-agent-{key}")
        if container is not None:
            self._verify_ownership(container, agent_id, username)
        return container

    async def _get_container(self, identifier: str) -> Any | None:
        try:
            return await asyncio.to_thread(self.client.containers.get, identifier)
        except NotFound:
            return None
        except (APIError, OSError) as exc:
            raise SandboxError(f"cannot inspect Docker container {identifier}: {exc}") from exc

    async def _create_container(
        self,
        key: str,
        agent_id: str,
        username: str,
        agent_path: Path,
        workspace_path: Path,
        state_path: Path,
    ) -> Any:
        image = self.config.sandbox.image
        resources = (await asyncio.to_thread(self.agent_catalog.load, agent_id)).resources
        try:
            await asyncio.to_thread(self.client.images.get, image)
        except ImageNotFound as exc:
            raise SandboxError(
                f"required image {image!r} is not present; acquire never pulls images"
            ) from exc

        port = self.config.sandbox.opencode_internal_port
        environment = {
            "XDG_CONFIG_HOME": "/opt/agent/global",
            "OPENCODE_DISABLE_AUTOUPDATE": "1",
            "OPENCODE_DISABLE_MODELS_FETCH": "1",
            "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
            "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",
        }
        labels = {
            "cloud.agent_id": agent_id,
            "cloud.username": username,
            "cloud.platform_instance": self.config.platform.instance_id,
            "cloud.image_version": image,
        }
        return await asyncio.to_thread(
            self.client.containers.create,
            image=image,
            name=f"cloud-agent-{key}",
            detach=True,
            init=True,
            log_config=docker.types.LogConfig(type="json-file", config={"max-size": "10m", "max-file": "3"}),
            environment=environment,
            labels=labels,
            read_only=self.config.sandbox.read_only_rootfs,
            tmpfs={
                "/tmp": f"rw,nosuid,nodev,size={self.config.sandbox.tmpfs_mb}m"
            },
            volumes={
                str(workspace_path): {"bind": "/workspace", "mode": "rw"},
                str(state_path): {"bind": "/state/opencode", "mode": "rw"},
                str(agent_path): {"bind": "/opt/agent", "mode": "ro"},
            },
            ports={f"{port}/tcp": ("127.0.0.1", None)},
            nano_cpus=int(resources.cpu_limit * 1_000_000_000),
            mem_limit=f"{resources.memory_mb}m",
            pids_limit=resources.pids_limit,
            runtime=self.config.sandbox.runtime,
            privileged=False,
            extra_hosts={"host.docker.internal": "host-gateway"},
        )

    async def _wait_ready(
        self, sandbox_id: str, container: Any, *, reused: bool
    ) -> SandboxEndpoint:
        started = time.perf_counter()
        try:
            return await self._poll_ready(sandbox_id, container, reused=reused)
        finally:
            if self.metrics is not None:
                self.metrics.sandbox_ready.observe(time.perf_counter() - started)

    async def _poll_ready(
        self, sandbox_id: str, container: Any, *, reused: bool
    ) -> SandboxEndpoint:
        deadline = time.monotonic() + self.config.sandbox.start_timeout_seconds
        last_problem = "health endpoint did not respond"
        first_probe = True
        while time.monotonic() < deadline:
            if not first_probe:
                await asyncio.to_thread(container.reload)
            first_probe = False
            if container.status != "running":
                last_problem = f"container status is {container.status}"
                break
            try:
                endpoint = self._endpoint(sandbox_id, container, reused=reused)
                payload = await self._health_probe(
                    f"{endpoint.base_url}{self.config.opencode.health_path}",
                    # Retry cold-start connections promptly across server initialization.
                    # The outer deadline and health/version checks remain authoritative.
                    min(2.0 if reused else 0.25, max(0.1, deadline - time.monotonic())),
                )
                if payload.get("healthy") is True and payload.get("version") == self.config.opencode.expected_version:
                    return endpoint
                last_problem = (
                    f"health payload mismatch: healthy={payload.get('healthy')!r}, "
                    f"version={payload.get('version')!r}"
                )
            except (httpx.HTTPError, SandboxError, ValueError) as exc:
                last_problem = str(exc)
            await asyncio.sleep(0.1)
        raise SandboxNotReadyError(
            f"sandbox {sandbox_id} was not ready before timeout: {last_problem}"
        )

    def _endpoint(self, sandbox_id: str, container: Any, *, reused: bool) -> SandboxEndpoint:
        port_key = f"{self.config.sandbox.opencode_internal_port}/tcp"
        bindings = container.attrs.get("NetworkSettings", {}).get("Ports", {}).get(port_key)
        if not bindings or len(bindings) != 1:
            raise SandboxError(f"container has no unique binding for {port_key}")
        binding = bindings[0]
        if binding.get("HostIp") not in {"127.0.0.1", "::1"}:
            raise SandboxError("OpenCode port is not bound exclusively to loopback")
        host_port = int(binding["HostPort"])
        return SandboxEndpoint(
            sandbox_id, container.id, host_port, f"http://127.0.0.1:{host_port}", reused
        )

    def _verify_ownership(self, container: Any, agent_id: str, username: str) -> None:
        labels = container.attrs.get("Config", {}).get("Labels") or {}
        expected = {
            "cloud.agent_id": agent_id,
            "cloud.username": username,
            "cloud.platform_instance": self.config.platform.instance_id,
            "cloud.image_version": self.config.sandbox.image,
        }
        mismatch = {key: labels.get(key) for key, value in expected.items() if labels.get(key) != value}
        if mismatch:
            raise SandboxOwnershipError(
                f"container {getattr(container, 'id', '<unknown>')} label mismatch: {mismatch}"
            )

    async def _persist(
        self,
        endpoint: SandboxEndpoint,
        agent_id: str,
        username: str,
        status: str,
    ) -> None:
        await asyncio.to_thread(
            self.registry.upsert_sandbox,
            sandbox_id=endpoint.sandbox_id,
            agent_id=agent_id,
            username=username,
            container_id=endpoint.container_id,
            host_port=endpoint.host_port,
            status=status,
            image_version=self.config.sandbox.image,
        )

    async def _remove_owned(self, container: Any) -> None:
        try:
            await asyncio.to_thread(container.remove, force=True)
        except NotFound:
            return
        except DockerException as exc:
            raise SandboxError(f"cannot remove failed sandbox {container.id}: {exc}") from exc

    def _agent_path(self, agent_id: str) -> Path:
        if hasattr(self, 'management'):
            definition = self.agent_catalog.load(agent_id)
            if definition.image != self.config.sandbox.image:
                raise SandboxError('Managed Agent image differs from platform image')
            return definition.path
        try:
            validate_identifier(agent_id, "agent_id")
        except WorkspacePathError as exc:
            raise SandboxError(str(exc)) from exc
        candidate = self.agents_root / agent_id
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise SandboxError(f"unknown Agent definition: {agent_id}") from exc
        if not resolved.is_relative_to(self._agents_root_real) or not resolved.is_dir():
            raise SandboxError(f"Agent definition escapes agents root: {agent_id}")
        if not (resolved / "opencode.json").is_file():
            raise SandboxError(f"Agent definition lacks opencode.json: {agent_id}")
        try:
            definition = self.agent_catalog.load(agent_id)
        except AgentDefinitionError as exc:
            raise SandboxError(str(exc)) from exc
        if definition.image != self.config.sandbox.image:
            raise SandboxError(
                f"Agent {agent_id} image differs from the pinned platform image"
            )
        return resolved

    @staticmethod
    async def _http_health_probe(url: str, timeout: float) -> dict[str, Any]:
        async with httpx.AsyncClient(trust_env=False, timeout=timeout, verify=_HEALTH_TLS_CONTEXT) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("health response is not a JSON object")
        return payload


# Architectural seam retained for callers while V1 has one concrete backend.
SandboxManager = LocalDockerBackend
