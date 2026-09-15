"""Exercise the pinned LiteLLM router against two credentials on an owned server."""
import asyncio
import json
import random
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


def test_real_router_balances_one_alias_across_independent_keys(monkeypatch):
    monkeypatch.setenv('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
    pytest.importorskip('litellm')
    from model_gateway.src.state import make_router
    from shared_libs.model_routing import deployment_entries, ROUTER_SETTINGS
    received = []

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            received.append((self.headers.get('Authorization'), payload['model']))
            body = json.dumps({'id': 'chatcmpl-test', 'object': 'chat.completion', 'created': 1,
                'model': payload['model'], 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'OK'}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    model = {'id': 'coding', 'provider': 'openai-compatible', 'upstream_model': 'gpt-4o-mini',
             'base_url': f'http://127.0.0.1:{server.server_port}/v1', 'deployments': [
                 {'id': 'a', 'api_key': 'account-a', 'rpm': 600, 'weight': 1},
                 {'id': 'b', 'api_key': 'account-b', 'rpm': 1200, 'weight': 2},
                 {'id': 'disabled', 'api_key': 'never-use', 'enabled': False}]}
    async def exercise():
        random.seed(42)
        router = make_router({'model_list': deployment_entries(model, require_credentials=True),
                              'router_settings': {**ROUTER_SETTINGS, 'num_retries': 0, 'timeout': 5}})
        for _ in range(24):
            reply = await router.acompletion(model='coding', messages=[{'role': 'user', 'content': 'OK'}], max_tokens=8)
            assert reply.choices[0].message.content == 'OK'
    try:
        asyncio.run(exercise())
        assert {key for key, _ in received} == {'Bearer account-a', 'Bearer account-b'}
        assert {model for _, model in received} == {'gpt-4o-mini'}
    finally:
        server.shutdown()
        server.server_close()
