from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from admin_web.local_service.server import create_local_app


@pytest.mark.parametrize('auth_status,ready_status', [(200,503),(200,200),(401,503),(403,503)])
def test_authentication_is_distinct_from_readiness(tmp_path, monkeypatch, auth_status, ready_status):
    paths = []
    real_client = httpx.AsyncClient
    def upstream(request):
        paths.append(request.url.path)
        assert request.headers['authorization'] == 'Bearer test-token'
        if request.url.path == '/cloud/capabilities':
            return httpx.Response(auth_status,json={'management': True})
        return httpx.Response(ready_status,json={'ok': ready_status==200,'modules': {'model_gateway': ready_status==200}})
    monkeypatch.setattr('admin_web.local_service.server.httpx.AsyncClient',lambda **kw: real_client(**kw,transport=httpx.MockTransport(upstream)))
    with TestClient(create_local_app(tmp_path,SimpleNamespace(url='http://upstream.test',token='test-token')),base_url='http://127.0.0.1') as client:
        csrf=client.get('/local/bootstrap').json()['csrf']
        response=client.post('/local/connection/test',json={},headers={'X-Local-CSRF':csrf})
        assert response.status_code == auth_status
        assert paths[0] == '/cloud/capabilities'
        if auth_status==200:
            assert response.json()['authenticated'] is True
            assert response.json()['ready']['ok'] == (ready_status==200)
        else:
            assert len(paths)==1
        assert 'test-token' not in response.text
