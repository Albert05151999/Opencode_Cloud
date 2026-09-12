import asyncio
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException

from test_operations import service
from test_agent_deletion import prepare
from app.job_coordinator import JobCoordinator


def test_force_preview_requires_exact_id_and_unchanged_activity(service,tmp_path):
    prepare(service,tmp_path)
    service.backend._get_container = AsyncMock(return_value=None)
    preview = asyncio.run(service.details.preview('sbx_delete'))
    assert preview['sessions']==['ses_delete'] and preview['execution']=='unknown'
    with pytest.raises(HTTPException):
        service.details.authorize('sbx_delete',preview['preview_id'],'wrong')
    service.recovery.invalidate_idle('agent-code')
    with pytest.raises(HTTPException):
        service.details.authorize('sbx_delete',preview['preview_id'],'sbx_delete')


def test_force_stop_records_interrupted_sessions_without_draining(service,tmp_path):
    prepare(service,tmp_path)
    service.backend._get_container = AsyncMock(return_value=None)
    preview = asyncio.run(service.details.preview('sbx_delete'))
    force = service.details.authorize('sbx_delete',preview['preview_id'],'sbx_delete')
    jid,_ = service.submit('sandbox.stop','sbx_delete','force-stop-key',force=force)
    asyncio.run(service.run(jid))
    job = service.store.read()[1]['jobs'][jid]
    assert job['status']=='succeeded' and job['interrupted_sessions']==['ses_delete']
    service.runtime.drain.assert_not_called()


def test_cancelled_queued_job_has_no_runtime_effect(service):
    jid,_ = service.submit('sandbox.restart','sbx_test','cancel-request')
    coordinator=JobCoordinator(service.store)
    coordinator.cancel(jid)
    asyncio.run(service.run(jid))
    service.runtime.drain.assert_not_called()
    assert coordinator.list()['items'][0]['status']=='cancelled'
