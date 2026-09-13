"""Real pinned LiteLLM against an owned loopback upstream; no provider spend."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from fastapi.testclient import TestClient


def test_real_router_activation_sse_runtime_auth_and_trace(tmp_path, monkeypatch):
    pytest.importorskip("litellm")
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    monkeypatch.setenv("MODEL_GATEWAY_TOKEN", "runtime-only-token")
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "default"))
    monkeypatch.setenv("LOG_ROOT", str(tmp_path / "log"))
    received = []

    class Upstream(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append((self.path, body, self.headers.get("Authorization")))
            assert self.headers.get("Authorization") == "Bearer upstream-only-token"
            assert self.headers.get("x-provider-required") == "preserved"
            assert self.headers.get("traceparent", "").startswith(
                "00-" + "1" * 32 + "-"
            )
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/event-stream" if body.get("stream") else "application/json",
            )
            self.end_headers()
            if body.get("stream"):
                for content, finish in [("hello", None), ("", "stop")]:
                    chunk = {
                        "id": "chatcmpl-local",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "local-test",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": content},
                                "finish_reason": finish,
                            }
                        ],
                    }
                    self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")
            else:
                self.wfile.write(
                    json.dumps(
                        {
                            "id": "chatcmpl-local",
                            "object": "chat.completion",
                            "created": 1,
                            "model": "local-test",
                            "choices": [
                                {
                                    "index": 0,
                                    "message": {
                                        "role": "assistant",
                                        "content": "hello",
                                    },
                                    "finish_reason": "stop",
                                }
                            ],
                            "usage": {
                                "prompt_tokens": 1,
                                "completion_tokens": 1,
                                "total_tokens": 2,
                            },
                        }
                    ).encode()
                )

        def log_message(self, *args):
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    try:
        from model_gateway.main import create_app

        config = {
            "data_root": str(tmp_path / "gateway"),
            "log_root": str(tmp_path / "log"),
            "service_token": "control-only-token",
        }
        with TestClient(create_app(config)) as client:
            client.headers["Authorization"] = "Bearer control-only-token"
            release = {
                "release_id": "real-router",
                "version": 1,
                "configuration": {
                    "model_list": [
                        {
                            "model_name": "sample",
                            "litellm_params": {
                                "model": "openai/local-test",
                                "api_base": f"http://127.0.0.1:{upstream.server_port}/v1",
                                "api_key": "upstream-only-token",
                                "extra_headers": {"x-provider-required": "preserved"},
                            },
                            "model_info": {"id": "sample"},
                        }
                    ],
                    "router_settings": {
                        "routing_strategy": "least-busy",
                        "num_retries": 2,
                        "timeout": 600,
                        "allowed_fails": 1,
                        "cooldown_time": 30,
                    },
                    "litellm_settings": {
                        "callbacks": ["cloud_logging.cloud_logger"],
                        "drop_params": False,
                    },
                },
            }
            assert (
                client.post("/internal/v1/config/validate", json=release).status_code
                == 200
            )
            assert (
                client.post("/internal/v1/config/activate", json=release).status_code
                == 200
            )
            client.headers["Authorization"] = "Bearer runtime-only-token"
            assert client.get("/internal/v1/config/status").status_code == 401
            trace_id = "1" * 32
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "sample",
                    "messages": [{"role": "user", "content": "local fixture"}],
                    "stream": True,
                },
                headers={"traceparent": f"00-{trace_id}-2222222222222222-01"},
            )
            assert response.status_code == 200, response.text
            assert "hello" in response.text and "data: [DONE]" in response.text
            assert received[0][0] == "/v1/chat/completions"
        records = [
            json.loads(line)
            for path in (tmp_path / "log").rglob("*.jsonl")
            for line in path.read_text().splitlines()
        ]
        assert any(event.get("trace_id") == trace_id for event in records)
        assert all(
            "upstream-only-token" not in json.dumps(event)
            and "local fixture" not in json.dumps(event)
            for event in records
        )
    finally:
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=3)
