import base64
import copy
from fastapi.testclient import TestClient
from catalog_service.main import create_app


def enable_seeded_defaults(app):
    from test.catalog_service.legacy_fixture import populate_legacy
    populate_legacy(app.state.store)
    with app.state.store.edit() as data:
        for model in data["models"].values():
            model["enabled"] = True
        for agent in data["agents"].values():
            agent["draft"]["enabled"] = True
            agent["versions"][0]["config"]["enabled"] = True


def test_fresh_install_can_prepare_first_managed_model_without_legacy_env(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SERVICE_TOKEN", "test-token")
    app = create_app(tmp_path)
    with TestClient(
        app, headers={"Authorization": "Bearer test-token"}
    ) as client:
        catalog = client.get("/cloud/admin/catalog").json()
        imported = client.post(
            "/cloud/admin/models/import",
            json={
                "revision": catalog["revision"],
                "models": [
                    {
                        "id": "my-model",
                        "name": "My model",
                        "provider": "openai-compatible",
                        "upstream_model": "upstream",
                        "base_url": "https://provider.example/v1",
                        "api_key": "secret",
                        "enabled": True,
                    }
                ],
            },
        )
        assert imported.status_code == 200, imported.text
        revision = client.get("/cloud/admin/catalog").json()["revision"]
        prepared = client.post(
            "/internal/v1/releases/prepare",
            json={"kind": "models.apply", "revision": revision},
        )
        assert prepared.status_code == 200, prepared.text
        assert [
            item["model_name"] for item in prepared.json()["configuration"]["model_list"]
        ] == ["my-model"]


def test_immutable_release_and_conditional_commit(tmp_path, monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", "test-token")
    app = create_app(tmp_path)
    enable_seeded_defaults(app)
    with TestClient(app, headers={"Authorization": "Bearer test-token"}) as client:
        catalog = client.get("/cloud/admin/catalog").json()
        payload = {
            "kind": "agent.apply",
            "target": "agent-code",
            "revision": catalog["revision"],
        }
        response = client.post("/internal/v1/releases/prepare", json=payload)
        assert response.status_code == 200, response.text
        release = response.json()
        assert "opencode.json" in release["files"]
        assert (
            client.get("/cloud/admin/catalog").json()["agents"]["agent-code"]["active"]
            == 1
        )
        # Later draft edits cannot alter an immutable compiled release.
        draft = copy.deepcopy(catalog["agents"]["agent-code"]["draft"])
        draft["instructions"] = "later edit"
        assert (
            client.put(
                "/cloud/admin/agents/agent-code", json={"config": draft}
            ).status_code
            == 200
        )
        assert (
            client.get("/internal/v1/releases/" + release["release_id"]).json()["files"]
            == release["files"]
        )
        committed = client.post(
            "/internal/v1/releases/" + release["release_id"] + "/commit", json={}
        )
        assert committed.status_code == 200, committed.text
        assert (
            client.post(
                "/internal/v1/releases/" + release["release_id"] + "/commit", json={}
            ).json()
            == committed.json()
        )
        bundle = client.get("/internal/v1/agents/agent-code/bundle").json()
        assert bundle["version"] == release["version"]
        assert base64.b64decode(bundle["files"]["AGENTS.md"]) != b"later edit"
        assert "releases" not in client.get("/cloud/admin/catalog").json()


def test_authentication_and_compilation_model_assignment(tmp_path, monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", "token")
    app = create_app(tmp_path)
    enable_seeded_defaults(app)
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/cloud/admin/catalog").status_code == 401
        client.headers["Authorization"] = "Bearer token"
        response = client.post(
            "/internal/v1/agents/agent-code/authorize",
            json={
                "method": "POST",
                "path": "session/ses_one/message",
                "payload": {"parts": []},
            },
        )
        assert response.status_code == 200, response.text
        assert (
            response.json()["payload"]["model"]["providerID"] == "cloud-model-gateway"
        )
        assert (
            client.post(
                "/internal/v1/agents/agent-code/authorize",
                json={"method": "POST", "path": "config", "payload": {}},
            ).status_code
            == 403
        )


def test_missing_immutable_history_is_not_silently_recompiled(tmp_path, monkeypatch):
    import shutil
    import pytest
    from pathlib import Path

    monkeypatch.setenv("SERVICE_TOKEN", "token")
    from test.catalog_service.legacy_fixture import populate_legacy
    from catalog_service.src.management import ManagementStore
    populate_legacy(ManagementStore(tmp_path, Path(__file__).resolve().parents[3] / 'catalog_service/resources/agents'))
    first = create_app(tmp_path)
    _, data = first.state.store.read()
    version = data["agents"]["agent-code"]["versions"][0]
    artifact = Path(version["path"])
    assert artifact.is_relative_to(tmp_path / "compiled")
    again = create_app(tmp_path)
    assert again.state.store.read()[1]["agents"]["agent-code"]["versions"][0][
        "path"
    ] == str(artifact)
    shutil.rmtree(artifact)
    with pytest.raises(RuntimeError, match="restore the immutable artifact"):
        create_app(tmp_path)
    assert not artifact.exists()
    assert first.state.store.read()[1]["agents"]["agent-code"]["versions"][0][
        "path"
    ] == str(artifact)


def test_disabled_model_import_and_update_preserve_disabled_agent_references(tmp_path,monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN","test-token")
    app=create_app(tmp_path)
    from test.catalog_service.legacy_fixture import populate_legacy
    populate_legacy(app.state.store)
    with app.state.store.edit() as data:
        for agent in data['agents'].values():
            agent['draft']['enabled'] = False
            for version in agent['versions']:
                version['config']['enabled'] = False
    with TestClient(app,headers={"Authorization":"Bearer test-token"}) as client:
        _,data=app.state.store.read()
        mid=next(iter(data['models']))
        references=app.state.store.model_references(data,mid)
        assert references
        model={'id':mid,'provider':'openai-compatible','upstream_model':'offline-unconfigured','base_url':'http://127.0.0.1:19090/v1','enabled':False}
        imported=client.post('/cloud/admin/models/import',json={'models':[model],'replace':True})
        assert imported.status_code==200,imported.text
        updated=client.put('/cloud/admin/models/'+mid,json={'model':model})
        assert updated.status_code==200,updated.text
        with app.state.store.edit() as changed:
            changed['agents'][references[0]]['draft']['enabled']=True
        blocked=client.post('/cloud/admin/models/import',json={'models':[model],'replace':True})
        assert blocked.status_code==409
        with app.state.store.edit() as changed:
            agent=changed['agents'][references[0]];agent['draft']['enabled']=False
            next(version for version in agent['versions'] if version['version']==agent['active'])['config']['enabled']=True
        blocked=client.put('/cloud/admin/models/'+mid,json={'model':model})
        assert blocked.status_code==409
