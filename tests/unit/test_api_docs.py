import copy
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api_docs as api_docs


def test_static_doc_preserves_native_schema_and_adds_routing_contract() -> None:
    source = json.loads(api_docs.UPSTREAM_SPEC.read_text(encoding="utf-8"))
    native_responses = copy.deepcopy(source["paths"]["/session/{sessionID}"]["get"]["responses"])
    native_session_schema = copy.deepcopy(source["components"]["schemas"]["Session"])
    application = FastAPI()
    application.include_router(api_docs.create_docs_router())

    response = TestClient(application).get("/doc")
    assert response.status_code == 200
    document = response.json()
    assert set(source["paths"]) <= set(document["paths"])
    assert document["paths"]["/session/{sessionID}"]["get"]["responses"] == native_responses
    assert document["components"]["schemas"]["Session"] == native_session_schema
    extension = document["x-cloud-routing"]
    assert extension["metadata"]["json_body"]["property"] == "_cloud"
    assert extension["resolution"]["session_paths"].startswith("The session ID")
    assert extension["websocket"]["pty_supported"] is False
    parameters = document["paths"]["/global/health"]["get"]["parameters"]
    assert {item["name"] for item in parameters} >= {
        "X-Cloud-Agent-ID", "X-Cloud-Username", "X-Cloud-Request-ID",
    }


def test_router_has_no_backend_dependency_and_missing_spec_fails_locally(monkeypatch, tmp_path: Path) -> None:
    router = api_docs.create_docs_router()
    endpoint = next(route.endpoint for route in router.routes if route.path == "/doc")
    assert endpoint.__code__.co_argcount == 0

    monkeypatch.setattr(api_docs, "UPSTREAM_SPEC", tmp_path / "missing.json")
    api_docs._document_bytes.cache_clear()
    with pytest.raises(RuntimeError, match="unavailable"):
        api_docs.create_docs_router()
    api_docs._document_bytes.cache_clear()
