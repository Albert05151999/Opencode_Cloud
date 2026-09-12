import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

from test_operations import service


def test_completed_start_is_reconciled_without_restarting(service):
    jid,_ = service.submit('sandbox.restart','sbx_test','restart-key')
    service.store.job(jid, checkpoint='start_requested',status='applying')
    container = SimpleNamespace(status='running',reload=Mock())
    service.backend._get_container = AsyncMock(return_value=container)
    service.backend._verify_ownership = Mock()
    service.backend.inspect = AsyncMock(return_value=object())
    asyncio.run(service.reconcile(jid))
    assert service.store.read()[1]['jobs'][jid]['status']=='succeeded'


def test_ambiguous_stop_does_not_repeat_docker_effect(service):
    jid,_ = service.submit('sandbox.restart','sbx_test','restart-key')
    service.store.job(jid, checkpoint='stop_requested',status='applying')
    container = SimpleNamespace(status='running',reload=Mock(),stop=Mock())
    service.backend._get_container = AsyncMock(return_value=container)
    service.backend._verify_ownership = Mock()
    asyncio.run(service.reconcile(jid))
    assert service.store.read()[1]['jobs'][jid]['status']=='failed'
    container.stop.assert_not_called()
