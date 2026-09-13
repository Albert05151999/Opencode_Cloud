from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from fastapi.testclient import TestClient
from admin_web.local_service.importer import jsonc, Importer
from admin_web.local_service.server import create_local_app
from admin_web.local_service.server import _correlation_headers


def test_jsonc_does_not_strip_urls_or_commas_in_strings():
    value = jsonc("""{/* comment */"url":"http://x/a,}","items":[1,2,],// note\n}""")
    assert value == {"url": "http://x/a,}", "items": [1, 2]}


def test_local_import_keeps_keys_out_of_preview(tmp_path, monkeypatch):
    directory = tmp_path / ".config/opencode"
    directory.mkdir(parents=True)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("TEST_IMPORT_KEY", "private-value")
    (directory / "opencode.jsonc").write_text(
        json.dumps(
            {
                "provider": {
                    "custom": {
                        "npm": "@ai-sdk/openai-compatible",
                        "options": {
                            "baseURL": "https://api.example/v1",
                            "apiKey": "{env:TEST_IMPORT_KEY}",
                        },
                        "models": {"fast": {"name": "Fast"}},
                    }
                }
            }
        )
    )
    importer = Importer(tmp_path)
    source = importer.discover()["sources"][0]
    preview = importer.preview(source["id"])
    assert not preview["errors"] and "private-value" not in json.dumps(preview)
    selected = importer.take(preview["preview_id"], ["custom-fast"])
    assert selected[0]["api_key"] == "private-value"


def test_local_host_origin_and_csrf(tmp_path):
    connection = SimpleNamespace(url="http://example.test", token="a" * 40)
    with TestClient(
        create_local_app(tmp_path, connection), base_url="http://127.0.0.1"
    ) as client:
        assert (
            client.get("/local/bootstrap", headers={"Host": "evil.example"}).status_code
            == 403
        )
        assert (
            client.get(
                "/local/bootstrap", headers={"Origin": "http://evil.example"}
            ).status_code
            == 403
        )
        assert client.post("/local/opencode/discover", json={}).status_code == 403
        csrf = client.get("/local/bootstrap").json()["csrf"]
        assert (
            client.post(
                "/local/opencode/discover", json={}, headers={"X-Local-CSRF": csrf}
            ).status_code
            == 200
        )


def test_correlation_headers_preserve_only_valid_context():
    valid = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
    assert _correlation_headers(
        {"traceparent": valid, "x-cloud-request-id": "request-1"}
    ) == {"traceparent": valid, "x-cloud-request-id": "request-1"}
    generated = _correlation_headers(
        {"traceparent": "invalid", "x-cloud-request-id": "bad value"}
    )
    assert generated["traceparent"] != "invalid"
    assert generated["x-cloud-request-id"].startswith("req_")


def test_remote_proxy_propagates_and_returns_trace_context(tmp_path, monkeypatch):
    captured = {}
    real_client = __import__("httpx").AsyncClient
    upstream_trace = "00-" + "c" * 32 + "-" + "d" * 16 + "-01"

    class Stream(__import__("httpx").AsyncByteStream):
        async def __aiter__(self):
            yield b"{}"

    async def upstream(request):
        captured.update(request.headers)
        return __import__("httpx").Response(
            200,
            stream=Stream(),
            headers={
                "content-type": "application/json",
                "traceparent": upstream_trace,
                "x-cloud-trace-id": "c" * 32,
                "x-cloud-request-id": "remote-request",
            },
        )

    def client_factory(**kwargs):
        kwargs["transport"] = __import__("httpx").MockTransport(upstream)
        return real_client(**kwargs)

    monkeypatch.setattr("admin_web.local_service.server.httpx.AsyncClient", client_factory)
    connection = SimpleNamespace(url="http://upstream.test", token="private-token")
    incoming = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
    with TestClient(
        create_local_app(tmp_path, connection), base_url="http://127.0.0.1"
    ) as client:
        response = client.get(
            "/remote/session/ses_1/message",
            headers={
                "traceparent": incoming,
                "x-cloud-request-id": "browser-request",
                "x-cloud-message-id": "msg_1",
                "x-cloud-session-id": "ses_1",
            },
        )
    assert captured["traceparent"] == incoming
    assert captured["x-cloud-request-id"] == "browser-request"
    assert captured["x-cloud-session-id"] == "ses_1"
    assert captured["x-cloud-message-id"] == "msg_1"
    assert response.headers["traceparent"] == upstream_trace
    assert response.headers["x-cloud-trace-id"] == "c" * 32
    assert response.headers["x-cloud-request-id"] == "remote-request"
@pytest.mark.parametrize(
    "adapter", ["openai-compatible", "openai", "anthropic", "google"]
)
def test_supported_import_adapters_preserve_defaults_and_parameters(tmp_path, adapter):
    source = tmp_path / "opencode.json"
    source.write_text(
        json.dumps(
            {
                "model": "sample/model-a",
                "small_model": "sample/model-a",
                "provider": {
                    "sample": {
                        "npm": "@ai-sdk/" + adapter,
                        "options": {
                            "apiKey": "fixture-private",
                            "baseURL": "https://example.test/v1",
                            "headers": {"x-fixture": "value"},
                        },
                        "models": {
                            "model-a": {
                                "options": {"temperature": 0.3},
                                "limit": {"context": 10000, "output": 2000},
                            }
                        },
                    }
                },
            }
        )
    )
    importer = Importer(tmp_path)
    found = next(
        s
        for s in importer.discover(file=str(source))["sources"]
        if Path(s["path"]) == source.resolve()
    )
    preview = importer.preview(found["id"])
    assert not preview["errors"]
    assert (
        preview["suggested_default_model_id"]
        == preview["suggested_small_model_id"]
        == "sample-model-a"
    )
    value = importer.take(preview["preview_id"], ["sample-model-a"])[0]
    assert value["provider"] == adapter and value["parameters"]["temperature"] == 0.3
    assert value["headers"][
        "x-fixture"
    ] == "value" and "fixture-private" not in json.dumps(preview)


def test_rendered_module_configuration_and_explicit_env_override(tmp_path, monkeypatch):
    from admin_web.local_service.configuration import load
    from admin_web.local_service.server import Connection

    rendered = tmp_path / "admin.json"
    rendered.write_text(
        json.dumps(
            {
                "module_id": "admin_web",
                "port": 18788,
                "data_root": str(tmp_path / "client-data"),
                "settings": {"gateway_url": "http://127.0.0.1:18090"},
            }
        )
    )
    monkeypatch.setenv("MODULE_CONFIG", str(rendered))
    assert load()["port"] == 18788
    assert Connection(tmp_path / "fresh").url == "http://127.0.0.1:18090"
    monkeypatch.setenv("ADMIN_WEB_PORT", "18789")
    assert load()["port"] == 18789
