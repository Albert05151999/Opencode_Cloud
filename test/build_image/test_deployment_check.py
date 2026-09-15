import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest

from config.tooling import deployment_check as check


def fake_docker(monkeypatch, port, *, binding=False):
    calls = []
    state = {'binding': binding}
    def command(root, *args):
        calls.append(args)
        if 'config' in args:
            return json.dumps({'services': {'api_gateway': {'ports': [
                {'target': 18080, 'published': str(port), 'host_ip': '127.0.0.1'}]}}})
        if 'ps' in args:
            return 'container-id'
        if 'inspect' in args:
            ports = {'18080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(port)}]} if state['binding'] else {}
            return json.dumps([{'State': {'Running': True}, 'NetworkSettings': {'Ports': ports}}])
        assert '--force-recreate' in args and args[-1] == 'api_gateway'
        state['binding'] = True
        return ''
    monkeypatch.setattr(check, 'command', command)
    return calls


def test_conflicting_listener_fails_without_stopping_anything(tmp_path, monkeypatch):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        calls = fake_docker(monkeypatch, listener.getsockname()[1])
        with pytest.raises(ValueError, match='occupied'):
            check.check(tmp_path, 'pre')
        assert not any('up' in call or 'stop' in call for call in calls)


def test_existing_own_binding_is_allowed(tmp_path, monkeypatch):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        fake_docker(monkeypatch, listener.getsockname()[1], binding=True)
        check.check(tmp_path, 'pre')


def test_missing_binding_recreates_only_gateway_and_checks_host_http(tmp_path, monkeypatch):
    paths = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        calls = fake_docker(monkeypatch, server.server_port)
        monkeypatch.setenv('http_proxy', 'http://127.0.0.1:1')
        check.check(tmp_path, 'post')
        assert paths == ['/cloud/health']
        assert sum('--force-recreate' in call for call in calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
