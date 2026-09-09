import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app.session_binding import SessionBindings, flattened_events
from app.workspace import WorkspaceManager


@pytest.mark.parametrize('failure',[False,True])
def test_native_binding_is_confirmed_and_failed_move_blocks_execution(tmp_path,failure):
    async def run():
        directory='/workspace';calls=[]
        def handle(request):
            nonlocal directory
            calls.append(request)
            if request.method=='POST':
                if failure:return httpx.Response(400,json={'error':'busy'})
                directory='/workspace/sessions/ses_test'
                return httpx.Response(204)
            return httpx.Response(200,json={'id':'ses_test','directory':directory})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            workspaces=WorkspaceManager(tmp_path/'work',tmp_path/'state')
            binding=SessionBindings(None,workspaces,client)
            route=SimpleNamespace(session_id='ses_test',agent_id='agent-code',username='alice')
            endpoint=SimpleNamespace(base_url='http://sandbox')
            if failure:
                with pytest.raises(HTTPException) as caught:await binding.ensure(endpoint,route)
                assert caught.value.status_code==409
            else:
                result=await binding.ensure(endpoint,route)
                assert result['directory']=='/workspace/sessions/ses_test'
                await binding.ensure(endpoint,route)
                assert sum(r.method=='POST' for r in calls)==1
            assert (tmp_path/'work/agent-code/alice/sessions/ses_test/outputs').is_dir()
    asyncio.run(run())


@pytest.mark.parametrize('compressed', [False, True])
def test_global_events_are_unwrapped_without_losing_initial_connection(compressed):
    async def run():
        content=b'data: {"type":"server.connected"}\n\ndata: {"directory":"/workspace/sessions/ses_a","payload":{"type":"session.idle","properties":{"sessionID":"ses_a"}}}\n\n'
        import gzip
        response=httpx.Response(200,content=gzip.compress(content) if compressed else content,
            headers={'content-encoding':'gzip'} if compressed else {})
        result=b''.join([chunk async for chunk in flattened_events(response)])
        assert b'server.connected' in result and b'ses_a' in result
        assert b'payload' not in result and b'directory' not in result
    asyncio.run(run())
