#!/usr/bin/env python3
"""Run the stage-13 sandbox lifecycle gate against the local Docker Engine."""

from __future__ import annotations

import asyncio
import atexit
import json
import shutil
from dataclasses import replace
from pathlib import Path

import docker

from app.config import load_config
from app.registry import Registry
from app.sandbox import LocalDockerBackend, sandbox_key
from app.workspace import WorkspaceManager


PROJECT = Path(__file__).resolve().parents[1]
TEST_ROOT = Path("/tmp/cloud-agent-sandbox-verification")
REPORT = PROJECT / "artifacts" / "sandbox" / "report.json"


def prepare_agents(root: Path) -> None:
    for agent_id in ("agent-code", "agent-data"):
        shutil.copytree(PROJECT / "agents" / agent_id, root / agent_id)


def remove_test_containers(client: docker.DockerClient) -> None:
    for agent_id, username in (
        ("agent-code", "alice"),
        ("agent-code", "bob"),
        ("agent-data", "alice"),
    ):
        name = f"cloud-agent-{sandbox_key(agent_id, username)}"
        try:
            container = client.containers.get(name)
        except docker.errors.NotFound:
            continue
        labels = container.attrs.get("Config", {}).get("Labels") or {}
        if labels.get("cloud.platform_instance") != "stage13-verification":
            raise RuntimeError(f"refusing to remove non-test container {name}")
        container.remove(force=True)


async def verify() -> dict[str, object]:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)
    agents_root = TEST_ROOT / "agents"
    prepare_agents(agents_root)

    config = load_config(PROJECT / "config.cfg")
    config = replace(config, platform=replace(config.platform, instance_id="stage13-verification"))
    registry = Registry(TEST_ROOT / "platform.db")
    registry.initialize()
    workspaces = WorkspaceManager(
        TEST_ROOT / "workspaces",
        TEST_ROOT / "state",
        runtime_uid=10001,
        runtime_gid=10001,
    )
    client = docker.from_env()
    client.ping()
    remove_test_containers(client)
    def cleanup() -> None:
        remove_test_containers(client)
        if TEST_ROOT.exists():
            shutil.rmtree(TEST_ROOT)

    atexit.register(cleanup)
    manager = LocalDockerBackend(config, registry, workspaces, agents_root, client=client)

    endpoints = await asyncio.gather(
        *(manager.acquire("agent-code", "alice") for _ in range(5))
    )
    alice = endpoints[0]
    assert len({item.container_id for item in endpoints}) == 1
    assert sum(not item.reused for item in endpoints) == 1

    bob, data_alice = await asyncio.gather(
        manager.acquire("agent-code", "bob"),
        manager.acquire("agent-data", "alice"),
    )
    assert len({alice.container_id, bob.container_id, data_alice.container_id}) == 3
    combinations = [
        ("agent-code", "alice", alice, "ALICE_CODE_SECRET.txt"),
        ("agent-code", "bob", bob, "BOB_CODE_SECRET.txt"),
        ("agent-data", "alice", data_alice, "ALICE_DATA_SECRET.txt"),
    ]
    for agent, user, _endpoint, marker in combinations:
        (TEST_ROOT / "workspaces" / agent / user / "shared" / marker).write_text(marker)
    isolation_checks = []
    for agent, user, endpoint, marker in combinations:
        container = client.containers.get(endpoint.container_id)
        actual_mounts = {item["Destination"]: item["Source"] for item in container.attrs["Mounts"]}
        expected_workspace = TEST_ROOT / "workspaces" / agent / user
        assert actual_mounts == {
            "/workspace": str(expected_workspace),
            "/state/opencode": str(TEST_ROOT / "state" / agent / user / "opencode"),
            "/opt/agent": str(agents_root / agent),
        }, actual_mounts
        probe = container.exec_run(["python", "-c", "from pathlib import Path; import json; print(json.dumps({'files': sorted(p.name for p in Path('/workspace/shared').iterdir()), 'host_path_visible': Path(" + repr(str(TEST_ROOT)) + ").exists()}))"])
        assert probe.exit_code == 0, probe.output
        observed = json.loads(probe.output)
        assert observed["files"] == [marker], observed
        assert observed["host_path_visible"] is False
        isolation_checks.append({"agent": agent, "username": user, "visible_marker": marker, "host_path_visible": False})
    first_session = workspaces.user_scope("agent-code", "alice", "session-one")
    second_session = workspaces.user_scope("agent-code", "alice", "session-two")
    (first_session / "marker.txt").write_text("same-user-session-one")
    (second_session / "marker.txt").write_text("same-user-session-two")
    same_user_probe = client.containers.get(alice.container_id).exec_run(["python", "-c", "from pathlib import Path; assert Path('/workspace/sessions/session-one/marker.txt').read_text() == 'same-user-session-one'; assert Path('/workspace/sessions/session-two/marker.txt').read_text() == 'same-user-session-two'"])
    assert same_user_probe.exit_code == 0, same_user_probe.output
    isolation_dir = PROJECT / "artifacts/isolation"
    isolation_dir.mkdir(parents=True, exist_ok=True)
    (isolation_dir / "report.json").write_text(json.dumps({"result": "passed", "checks": isolation_checks, "same_user_sessions_share_workspace": True}, indent=2) + "\n")

    alice_container = client.containers.get(alice.container_id)
    mounts = {mount["Destination"]: mount for mount in alice_container.attrs["Mounts"]}
    alice_root = (TEST_ROOT / "workspaces" / "agent-code" / "alice").resolve()
    bob_root = (TEST_ROOT / "workspaces" / "agent-code" / "bob").resolve()
    assert mounts["/workspace"]["Source"] == str(alice_root)
    assert all(not Path(mount["Source"]).is_relative_to(bob_root) for mount in mounts.values())
    assert set(mounts) == {"/workspace", "/state/opencode", "/opt/agent"}
    assert mounts["/workspace"]["RW"] is True
    assert mounts["/state/opencode"]["RW"] is True
    assert mounts["/opt/agent"]["RW"] is False
    host_config = alice_container.attrs["HostConfig"]
    assert host_config["ReadonlyRootfs"] is True
    assert host_config["Privileged"] is False
    assert host_config["Runtime"] == "runc"
    assert host_config["NanoCpus"] == int(config.sandbox.default_cpu * 1_000_000_000)
    assert host_config["Memory"] == config.sandbox.default_memory_mb * 1024 * 1024
    assert host_config["PidsLimit"] == config.sandbox.default_pids
    assert f"size={config.sandbox.tmpfs_mb}m" in host_config["Tmpfs"]["/tmp"]
    assert "host.docker.internal:host-gateway" in host_config["ExtraHosts"]
    assert not any(mount["Source"] == "/var/run/docker.sock" for mount in mounts.values())

    expected_labels = {
        "cloud.agent_id": "agent-code",
        "cloud.username": "alice",
        "cloud.platform_instance": "stage13-verification",
        "cloud.image_version": config.sandbox.image,
    }
    labels = alice_container.attrs["Config"]["Labels"]
    assert all(labels.get(key) == value for key, value in expected_labels.items())
    environment = set(alice_container.attrs["Config"]["Env"])
    for name in (
        "OPENCODE_DISABLE_AUTOUPDATE",
        "OPENCODE_DISABLE_MODELS_FETCH",
        "OPENCODE_DISABLE_DEFAULT_PLUGINS",
        "OPENCODE_DISABLE_LSP_DOWNLOAD",
    ):
        assert f"{name}=1" in environment
    port_binding = host_config["PortBindings"][f"{config.sandbox.opencode_internal_port}/tcp"]
    assert len(port_binding) == 1 and port_binding[0]["HostIp"] == "127.0.0.1"
    uid = alice_container.exec_run(["id", "-u"])
    assert uid.exit_code == 0 and uid.output.strip() == b"10001"

    result = alice_container.exec_run(
        ["sh", "-lc", "echo workspace-ok > /workspace/shared/stage13.txt; echo state-ok > /state/opencode/stage13.txt"]
    )
    assert result.exit_code == 0, result.output.decode(errors="replace")

    alice_container.stop(timeout=2)
    restarted = await manager.acquire("agent-code", "alice")
    assert restarted.container_id == alice.container_id
    assert restarted.reused is True
    assert (alice_root / "shared" / "stage13.txt").read_text().strip() == "workspace-ok"

    report = {
        "result": "passed",
        "docker_sdk_version": docker.__version__,
        "image": config.sandbox.image,
        "concurrent_acquires": len(endpoints),
        "unique_container_count_for_same_key": 1,
        "isolated_container_count": 3,
        "alice_host_port": restarted.host_port,
        "checks": [
            "five concurrent same-key acquires create one container",
            "different Agent/User keys create distinct containers",
            "authoritative labels and loopback random ports",
            "read-only rootfs, runc, tmpfs, resource limits, no privileged mode",
            "exact workspace/state/agent mounts with Alice/Bob isolation",
            "UID 10001 can write workspace and state",
            "stopped sandbox restarts with persistent data",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    cleanup()
    atexit.unregister(cleanup)
    return report


if __name__ == "__main__":
    print(json.dumps(asyncio.run(verify()), indent=2))
