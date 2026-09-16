import json
import os
import time

import httpx
from fastapi.testclient import TestClient

from observability.main import create_app
from shared_libs.logging import TRACE_CONTEXT
from shared_libs.service import internal_sync_client


def config(tmp_path):
    return {
        "data_root": str(tmp_path / "data"),
        "log_root": str(tmp_path / "log"),
        "service_token": "internal",
        "settings": {"retention_days": 2},
        "services": {"catalog_service": "http://catalog.test"},
    }


def test_authenticated_bounded_trace_query_and_retention(tmp_path):
    cfg = config(tmp_path)
    folder = tmp_path / "log" / "operations" / "worker"
    folder.mkdir(parents=True)
    trace = "a" * 32
    events = [
        {
            "timestamp": f"2026-09-12T00:00:{n:02d}",
            "trace_id": trace,
            "span_id": f"{n:016x}",
            "job_id": "job-1",
            "module": "operations",
        }
        for n in range(10)
    ]
    (folder / "events.jsonl").write_text(
        "\n".join(map(json.dumps, events)) + "\nnot json\n[]\n"
    )
    old = folder / "events.jsonl.1"
    old.write_text("old\n")
    os.utime(old, (time.time() - 3 * 86400,) * 2)
    application = create_app(cfg)
    application.state.prune()
    assert not old.exists() and (folder / "events.jsonl").exists()
    client = TestClient(application)
    assert client.get("/cloud/logs").status_code == 401
    client.headers["Authorization"] = "Bearer internal"
    result = client.get(
        "/cloud/logs", params={"module": "operations", "job_id": "job-1", "limit": 2}
    ).json()
    assert (
        len(result["items"]) == 2
        and result["items"][0] == events[-1]
        and result["truncated"]
    )
    detail = client.get("/cloud/traces/" + trace).json()
    assert len(detail["spans"]) == len(events)
    assert all(span["duration_ms"] is None for span in detail["spans"])
    assert detail["summary"]["span_count"] == len(events)
    assert detail["summary"]["duration_ms"] is None
    assert not detail["partial"] and detail["coverage"]["retention_days"] == 2
    assert (
        client.get("/cloud/logs", params={"module": "../elsewhere"}).status_code == 400
    )
    assert client.get("/metrics").status_code == 200


def test_trace_aggregates_span_tree_module_intervals_and_recent_list(tmp_path):
    cfg=config(tmp_path)
    folder=tmp_path/'log'/'api_gateway'; folder.mkdir(parents=True)
    trace='b'*32
    events=[
        {'timestamp':'2026-09-12T00:00:01+00:00','trace_id':trace,'span_id':'1'*16,'module':'api_gateway','action':'http_request','method':'POST','path':'/session/ses_demo/message','duration_ms':100,'status_code':200,'session_id':'ses_demo'},
        {'timestamp':'2026-09-12T00:00:00.980000+00:00','trace_id':trace,'span_id':'2'*16,'parent_span_id':'1'*16,'module':'api_gateway','action':'stage_complete','stage':'proxy','duration_ms':30},
        {'timestamp':'2026-09-12T00:00:01.050000+00:00','trace_id':trace,'span_id':'3'*16,'module':'catalog_service','action':'http_request','duration_ms':20,'error_code':'TimeoutError'},
        {'timestamp':'2026-09-12T00:00:01.070000+00:00','trace_id':trace,'span_id':'4'*16,'parent_span_id':'f'*16,'module':'sandbox_manager','action':'external_child','level':'error'},
    ]
    (folder/'events.jsonl').write_text('\n'.join(map(json.dumps,events))+'\n')
    client=TestClient(create_app(cfg)); client.headers['Authorization']='Bearer internal'
    detail=client.get('/cloud/traces/'+trace).json()
    assert detail['span_tree']['roots']==['1'*16,'3'*16,'4'*16]
    parent=next(span for span in detail['spans'] if span['span_id']=='1'*16)
    assert parent['children']==['2'*16] and parent['offset_ms']==0.0
    external=next(span for span in detail['spans'] if span['span_id']=='4'*16)
    assert external['external_parent'] and external['duration_ms'] is None
    assert external['status']=='error' and external['events']==[events[-1]]
    assert not detail['partial']
    assert detail['summary']['module_duration_ms']=={'api_gateway':100.0,'catalog_service':20.0}
    assert detail['summary']['modules']==['api_gateway','catalog_service','sandbox_manager']
    assert detail['summary']['span_count']==4 and detail['summary']['event_count']==4
    assert detail['summary']['duration_ms']==170.0
    assert detail['summary']['external_parent_count']==1
    assert detail['summary']['error_span_count']==2
    assert detail['summary']['completeness']=='scanned_retention_window_only'
    listed=client.get('/cloud/traces',params={'session_id':'ses_demo'}).json()
    assert listed['items'][0]['trace_id']==trace and listed['items'][0]['error']
    assert listed['items'][0]['modules']==['api_gateway','catalog_service','sandbox_manager']
    assert listed['items'][0]['method']=='POST' and listed['items'][0]['path']=='/session/ses_demo/message'
    assert listed['items'][0]['duration_ms']==100.0 and listed['items'][0]['operation']=='http_request'
    assert client.get('/cloud/traces',params={'trace_id':trace}).json()['items'][0]['trace_id']==trace
    assert client.get('/cloud/traces',params={'trace_id':'bad'}).status_code==400
    assert client.get('/cloud/traces',params={'session_id':'../bad'}).status_code==400


def test_trace_scan_reports_partial_when_byte_budget_omits_history(tmp_path):
    cfg=config(tmp_path); cfg['settings']['trace_scan_bytes']=1024*1024
    folder=tmp_path/'log'/'api_gateway'; folder.mkdir(parents=True)
    trace='c'*32
    first=json.dumps({'timestamp':'2026-09-12T00:00:00+00:00','trace_id':trace,'span_id':'4'*16})+'\n'
    (folder/'events.jsonl').write_text(first + ('x'*100+'\n')*11000)
    client=TestClient(create_app(cfg)); client.headers['Authorization']='Bearer internal'
    detail=client.get('/cloud/traces/'+trace).json()
    assert detail['events']==[] and detail['truncated'] and detail['partial']
    assert detail['coverage']['bytes_scanned']==1024*1024


def test_recent_traces_hide_only_pure_health_traces(tmp_path):
    cfg = config(tmp_path)
    folder = tmp_path / "log" / "api_gateway"
    folder.mkdir(parents=True)
    health_trace = "e" * 32
    business_trace = "f" * 32
    events = [
        {"timestamp": "2026-09-12T00:00:01+00:00", "trace_id": health_trace,
         "span_id": "8" * 16, "module": "api_gateway", "action": "http_request",
         "method": "GET", "path": "/cloud/health/ready", "duration_ms": 2},
        {"timestamp": "2026-09-12T00:00:02+00:00", "trace_id": business_trace,
         "span_id": "9" * 16, "module": "api_gateway", "action": "http_request",
         "method": "GET", "path": "/metrics", "duration_ms": 3, "session_id": "ses_work"},
        {"timestamp": "2026-09-12T00:00:02.100000+00:00", "trace_id": business_trace,
         "span_id": "a" * 16, "module": "agent_runtime", "action": "model_dispatch",
         "event_kind": "instant", "message_id": "msg_work", "session_id": "ses_work"},
    ]
    (folder / "events.jsonl").write_text("\n".join(map(json.dumps, events)) + "\n")
    client = TestClient(create_app(cfg))
    client.headers["Authorization"] = "Bearer internal"

    listed = client.get("/cloud/traces", params={"session_id": "ses_work"}).json()
    assert [item["trace_id"] for item in listed["items"]] == [business_trace]
    assert listed["items"][0]["message_id"] == "msg_work"
    assert listed["items"][0]["modules"] == ["agent_runtime", "api_gateway"]
    unfiltered = client.get("/cloud/traces").json()
    assert [item["trace_id"] for item in unfiltered["items"]] == [business_trace]
    including_health = client.get("/cloud/traces", params={"exclude_health": False}).json()
    assert {health_trace, business_trace} <= {
        item["trace_id"] for item in including_health["items"]
    }


def test_trace_tolerates_invalid_durations_and_breaks_parent_cycles(tmp_path):
    cfg = config(tmp_path)
    folder = tmp_path / "log" / "operations"
    folder.mkdir(parents=True)
    trace = "d" * 32
    events = [
        {"timestamp": "2026-09-12T00:00:01+00:00", "trace_id": trace,
         "span_id": "5" * 16, "parent_span_id": "6" * 16,
         "module": "operations", "duration_ms": float("nan")},
        {"timestamp": "2026-09-12T00:00:02+00:00", "trace_id": trace,
         "span_id": "6" * 16, "parent_span_id": "5" * 16,
         "module": "operations", "duration_ms": float("inf")},
        {"timestamp": "2026-09-12T00:00:03+00:00", "trace_id": trace,
         "span_id": "7" * 16, "parent_span_id": "7" * 16,
         "module": "operations", "duration_ms": 10**300},
    ]
    (folder / "events.jsonl").write_text("\n".join(map(json.dumps, events)) + "\n")
    client = TestClient(create_app(cfg))
    client.headers["Authorization"] = "Bearer internal"

    response = client.get("/cloud/traces/" + trace)
    assert response.status_code == 200
    detail = response.json()
    assert all(span["duration_ms"] is None for span in detail["spans"])
    assert all(span["cycle_broken"] for span in detail["spans"])
    assert set(detail["span_tree"]["roots"]) == {"5" * 16, "6" * 16, "7" * 16}
    assert detail["summary"]["module_duration_ms"] == {}
    assert detail["summary"]["modules"] == ["operations"]


def test_sync_http_boundary_preserves_background_job_context(tmp_path):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    token = TRACE_CONTEXT.set(
        {
            "trace_id": "a" * 32,
            "span_id": "b" * 16,
            "job_id": "job-123",
            "request_id": "request-123",
            "session_id": "ses_a",
            "message_id": "msg_a",
        }
    )
    try:
        with internal_sync_client(
            config(tmp_path), "catalog_service", transport=httpx.MockTransport(handle)
        ) as client:
            client.get("/internal/v1/status")
    finally:
        TRACE_CONTEXT.reset(token)
    headers = seen[0].headers
    assert headers["traceparent"] == "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
    assert headers["x-cloud-job-id"] == "job-123"
    assert headers["x-cloud-request-id"] == "request-123"
    assert headers["x-cloud-session-id"] == "ses_a"
    assert headers["x-cloud-message-id"] == "msg_a"
    assert headers["authorization"] == "Bearer internal"
def test_log_export_includes_retained_rows_beyond_preview_and_filters_session(tmp_path):
    cfg = config(tmp_path)
    folder = tmp_path / "log" / "operations" / "worker"
    folder.mkdir(parents=True)
    rows = [{"module":"operations", "trace_id":"a"*32, "session_id":"ses_one", "n":n} for n in range(1100)]
    (folder / "events.jsonl").write_text("\n".join(map(json.dumps, rows)) + '\n')
    (folder / "events.jsonl.1").write_text(json.dumps({"module":"operations", "session_id":"ses_two"})+'\n')
    client = TestClient(create_app(cfg), headers={"Authorization":"Bearer internal"})
    preview = client.get('/cloud/logs?module=operations&session_id=ses_one&limit=100').json()
    assert len(preview['items']) == 100 and preview['truncated']
    exported = client.get('/cloud/logs/export?module=operations&session_id=ses_one&trace_id='+'a'*32)
    assert exported.status_code == 200
    assert 'attachment' in exported.headers['content-disposition']
    assert [json.loads(line) for line in exported.text.splitlines()] == rows
    assert client.get('/cloud/logs/export?module=../escape').status_code == 400


def test_session_only_traces_are_filtered_before_result_limit(tmp_path):
    cfg = config(tmp_path)
    folder = tmp_path / "log" / "api_gateway" / "worker"
    folder.mkdir(parents=True)
    rows = [{"timestamp":f"2026-09-16T01:00:0{n}Z", "trace_id":str(n)*32,
             "span_id":str(n)*16,"module":"api_gateway","action":"http_request",
             "path":"/session","session_id":"ses_one" if n == 1 else None} for n in range(1,4)]
    (folder/'events.jsonl').write_text('\n'.join(map(json.dumps,rows)))
    client=TestClient(create_app(cfg),headers={"Authorization":"Bearer internal"})
    result=client.get('/cloud/traces?session_only=true&limit=1').json()
    assert len(result['items']) == 1 and result['items'][0]['trace_id'] == '1'*32
