import base64
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from sandbox_manager.catalog_client import install_bundle


def bundle(content=b"fixture"):
    return {"version": 1, "files": {"agent.cfg": base64.b64encode(content).decode()}}


def test_parallel_immutable_install_and_conflict(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(
            pool.map(
                lambda _: install_bundle(tmp_path, "agent-code", bundle()), range(32)
            )
        )
    assert len(set(paths)) == 1
    assert paths[0].joinpath("agent.cfg").read_bytes() == b"fixture"
    assert not list(tmp_path.rglob(".bundle-*"))
    with pytest.raises(HTTPException) as conflict:
        install_bundle(tmp_path, "agent-code", bundle(b"different"))
    assert conflict.value.status_code == 409


@pytest.mark.parametrize("value", ["not base64!", 123, None])
def test_invalid_bundle_encoding_is_client_error(tmp_path, value):
    with pytest.raises(HTTPException) as error:
        install_bundle(
            tmp_path, "agent-code", {"version": 1, "files": {"agent.cfg": value}}
        )
    assert error.value.status_code == 422
    assert not list(tmp_path.rglob(".bundle-*"))


def full_bundle(version=1, key="{env:MODEL_GATEWAY_TOKEN}"):
    import json

    cfg = "[agent]\nid=agent-code\ndisplay_name=Code\nimage=runtime:test\nidle_timeout_seconds=1800\n[resources]\ncpu_limit=1\nmemory_mb=512\npids_limit=128\n[models]\ndefault=sample\nallowed=sample\n"
    opencode = {
        "share": "disabled",
        "autoupdate": False,
        "enabled_providers": ["cloud-model-gateway"],
        "model": "cloud-model-gateway/sample",
        "instructions": ["/opt/agent/AGENTS.md"],
        "provider": {
            "cloud-model-gateway": {
                "npm": "@ai-sdk/openai-compatible",
                "options": {"baseURL": "http://model.test/v1", "apiKey": key},
                "models": {"sample": {}},
            }
        },
    }
    files = {
        "agent.cfg": cfg,
        "opencode.json": json.dumps(opencode),
        "AGENTS.md": "Test agent",
    }
    return {
        "version": version,
        "files": {k: base64.b64encode(v.encode()).decode() for k, v in files.items()},
    }


def test_staged_bundle_survives_restart_until_catalog_commit(tmp_path):
    import httpx
    from sandbox_manager.catalog_client import RemoteCatalog

    config = {
        "services": {"catalog_service": "http://catalog.test"},
        "service_token": "service",
    }
    current = [full_bundle(1)]

    def transport(request):
        assert request.headers["Authorization"] == "Bearer service"
        return httpx.Response(200, json=current[0])

    catalog = RemoteCatalog(config, tmp_path, "http://model.test/v1")
    catalog.client.close()
    catalog.client = httpx.Client(
        transport=httpx.MockTransport(transport),
        base_url="http://catalog.test",
        headers={"Authorization": "Bearer service"},
    )
    assert catalog.load("agent-code").path.parent.name == "1"
    staged = install_bundle(tmp_path, "agent-code", full_bundle(2))
    catalog.stage("agent-code", staged)
    restarted = RemoteCatalog(config, tmp_path, "http://model.test/v1")
    restarted.client.close()
    restarted.client = catalog.client
    assert restarted.load("agent-code").path.parent.name == "2"
    with pytest.raises(HTTPException) as pending:
        restarted.commit("agent-code")
    assert pending.value.status_code == 409
    current[0] = full_bundle(2)
    assert restarted.commit("agent-code").path.parent.name == "2"
    assert restarted.overrides == {}
    assert "agent-code" not in (tmp_path / "applied.json").read_text()
    catalog.client.close()


def test_staging_persistence_failure_does_not_change_memory(tmp_path, monkeypatch):
    from sandbox_manager.catalog_client import RemoteCatalog

    catalog = RemoteCatalog(
        {
            "services": {"catalog_service": "http://catalog.test"},
            "service_token": "service",
        },
        tmp_path,
        "http://model.test/v1",
    )
    path = install_bundle(tmp_path, "agent-code", full_bundle())

    def fail(_):
        raise OSError("disk full")

    monkeypatch.setattr(catalog, "_persist", fail)
    with pytest.raises(OSError):
        catalog.stage("agent-code", path)
    assert catalog.overrides == {}
    catalog.client.close()


def test_bundle_rejects_embedded_model_credential(tmp_path):
    from sandbox_manager.catalog_client import RemoteCatalog

    catalog = RemoteCatalog(
        {
            "services": {"catalog_service": "http://catalog.test"},
            "service_token": "service",
        },
        tmp_path,
        "http://model.test/v1",
    )
    path = install_bundle(tmp_path, "agent-code", full_bundle(key="embedded-secret"))
    with pytest.raises(HTTPException) as error:
        catalog.stage("agent-code", path)
    assert error.value.status_code == 422
    catalog.client.close()


def test_installed_bundle_is_checked_without_staging_writes(tmp_path, monkeypatch):
    path = install_bundle(tmp_path, "agent-code", bundle())
    def no_staging(*args, **kwargs):
        raise AssertionError("Hot immutable verification must not rewrite bundle")
    monkeypatch.setattr("sandbox_manager.catalog_client.tempfile.mkdtemp", no_staging)
    assert install_bundle(tmp_path, "agent-code", bundle()) == path
    path.joinpath("agent.cfg").write_bytes(b"tampered")
    with pytest.raises(HTTPException) as error:
        install_bundle(tmp_path, "agent-code", bundle())
    assert error.value.status_code == 409


def test_monitor_classifies_normal_users_without_admission_but_checks_load_tombstones():
    from sandbox_manager.catalog_client import Admission
    admission=object.__new__(Admission)
    calls=[]
    def denied(*args):
        calls.append(args)
        raise HTTPException(409,'stopped or tombstoned')
    admission.resources_for=denied
    admission.blocked=set()
    assert admission.active_user('agent-code','manually-stopped') is False
    assert calls==[]
    with pytest.raises(HTTPException):admission.active_user('agent-code','loadtest-expired-0')
    with pytest.raises(HTTPException):admission.check_acquire('agent-code','manually-stopped')
    assert len(calls)==2
