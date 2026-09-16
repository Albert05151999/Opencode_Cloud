import json
from fastapi.testclient import TestClient
from observability.main import create_app
from observability.session_timeline import session_timeline


def event(n, module, action, **extra):
    return dict(timestamp=f'2026-09-16T10:00:{n:02d}+00:00', module=module, action=action,
                trace_id='a'*32, span_id=f'{n:016x}', session_id='ses_test', **extra)


def test_turns_include_runtime_models_and_tools_without_double_counting_or_polling():
    rows=[event(1,'api_gateway','http_request',path='/session/ses_test/prompt_async',method='POST',duration_ms=5),
          event(2,'agent_runtime','model_dispatch',message_id='msg_'+'a'*32),
          event(4,'model_gateway','http_request',method='POST',duration_ms=1800),
          event(4,'model_gateway','model.completed',duration_ms=1790),
          event(5,'agent_runtime','tool_complete',duration_ms=30,tool='bash'),
          event(6,'agent_runtime','model_dispatch',message_id='msg_'+'a'*32),
          event(8,'model_gateway','http_request',method='POST',duration_ms=1500),
          event(8,'agent_runtime','runtime_complete',duration_ms=7000),
          event(9,'api_gateway','http_request',method='GET',path='/session/ses_test/message',duration_ms=10)]
    second=event(12,'api_gateway','http_request',method='POST',path='/session/ses_test/prompt_async',duration_ms=5)
    second['trace_id']='b'*32
    rows.append(second)
    result=session_timeline(list(reversed(rows)))
    assert len(result['items']) == 2
    first=result['items'][0]
    assert first['model_calls']==2 and first['runtime_observed']
    assert [p['kind'] for p in first['phases']]==['model','tool','model']
    assert first['phases'][0]['duration_ms']==1800
    assert first['runtime']['duration_ms']==7000 and len(first['requests'])==1
    assert not result['items'][1]['runtime_observed']
    assert session_timeline(rows,1)['truncated']


def test_session_endpoint_filters_before_limit_and_preserves_uncorrelated_runtime(tmp_path):
    cfg={'data_root':str(tmp_path/'data'),'log_root':str(tmp_path/'logs'),'service_token':'internal','settings':{},'services':{}}
    folder=tmp_path/'logs'/'agent_runtime'/'test';folder.mkdir(parents=True)
    runtime=event(2,'agent_runtime','model_dispatch',message_id='native-message')
    runtime.pop('trace_id');runtime.pop('span_id')
    noise=[{**event(3,'api_gateway','http_request',method='GET'), 'session_id':'ses_other'} for _ in range(1100)]
    (folder/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in [runtime,*noise]))
    client=TestClient(create_app(cfg),headers={'Authorization':'Bearer internal'})
    result=client.get('/cloud/traces/sessions/ses_test')
    assert result.status_code==200
    turn=result.json()['items'][0]
    assert not turn['runtime_observed'] and turn['trace_ids']==[]
    assert turn['runtime'] is None and turn['phases']==[]
    assert client.get('/cloud/traces/sessions/invalid!').status_code==400


def test_native_message_identity_links_dispatch_without_trace_to_model_response():
    dispatch=event(2,'agent_runtime','model_dispatch',message_id='native-user-message')
    dispatch.pop('trace_id')
    response=event(4,'model_gateway','http_request',message_id='native-user-message',duration_ms=1800)
    result=session_timeline([response,dispatch])
    assert len(result['items'])==1
    assert not result['items'][0]['runtime_observed'] and result['items'][0]['model_calls']==1
