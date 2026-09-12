import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

import httpx

from app.providers import ProviderService
from test_operations import service


def test_draft_model_probe_uses_isolation_and_always_removes_credentials(service):
    runtime = service.runtime
    baseline = copy.deepcopy(service.store.read())
    container = SimpleNamespace(attrs={'NetworkSettings': {'Ports': {'4000/tcp': [{'HostPort': '43210'}]}}}, reload=Mock(), remove=Mock())
    runtime.gateway_container = Mock(return_value=SimpleNamespace(image=SimpleNamespace(id='test-image')))
    runtime.backend.config = SimpleNamespace(platform=SimpleNamespace(instance_id='test-platform'))
    runtime.backend.client = SimpleNamespace(containers=SimpleNamespace(run=Mock(return_value=container)))
    runtime.gateway_configuration = Mock(return_value={'model_list': [{'model_name': 'demo'}]})
    runtime.client = SimpleNamespace(get=AsyncMock(return_value=httpx.Response(200)), post=AsyncMock(return_value=httpx.Response(401)))
    model = {'id': 'demo', 'name': 'Demo', 'provider': 'openai-compatible', 'upstream_model': 'upstream',
             'base_url': 'https://example.org/v1', 'api_key': 'private-probe-key', 'parameters': {}, 'enabled': True}
    result = asyncio.run(ProviderService(runtime).test(model))
    assert result['error'] == 'credentials' and result['published'] is False
    assert service.store.read() == baseline
    container.remove.assert_called_once_with(force=True)
    assert list((service.store.root / 'model-probes').iterdir()) == []
    kwargs = runtime.backend.client.containers.run.call_args.kwargs
    assert kwargs['ports']['4000/tcp'][0] == '127.0.0.1'
    assert all(value['mode'] == 'ro' for value in kwargs['volumes'].values())
