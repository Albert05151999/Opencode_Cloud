import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

WRITER=Path(__file__).resolve().parents[2]/'build_image/modules/agent_runtime/runtime-log.py'

def test_exit_output_redaction_and_rotation(tmp_path):
    env=dict(os.environ,RUNTIME_LOG_DIR=str(tmp_path),SANDBOX_ID='sbx_test',RUNTIME_LOG_MAX_BYTES='1024',RUNTIME_LOG_BACKUP_COUNT='2')
    child="import os,sys; [os.write(1,b'api_key=SECRET prompt=PRIVATE'*1000) for _ in range(10)]; sys.exit(7)"
    result=subprocess.run([sys.executable,str(WRITER),sys.executable,'-c',child],env=env,capture_output=True,text=True,timeout=10)
    assert result.returncode==7
    assert 'SECRET' not in result.stdout and 'PRIVATE' not in result.stdout
    files=list(tmp_path.glob('events.jsonl*')); assert 1<=len(files)<=3
    for path in files:
        assert path.stat().st_size<=1024
        for line in path.read_text().splitlines():
            event=json.loads(line); assert event['module']=='agent_runtime' and event['sandbox_id']=='sbx_test'
            assert 'SECRET' not in line and 'PRIVATE' not in line
    assert json.loads((tmp_path/'events.jsonl').read_text().splitlines()[-1])['exit_code']==7
    assert (tmp_path/'events.jsonl').stat().st_mode & 0o777 == 0o644

def test_signal_forwarding_preserves_child_exit(tmp_path):
    env=dict(os.environ,RUNTIME_LOG_DIR=str(tmp_path),SANDBOX_ID='sbx_test')
    marker=tmp_path/'ready'
    child="import signal,sys,time,pathlib; signal.signal(signal.SIGTERM,lambda *_:sys.exit(23)); pathlib.Path(sys.argv[1]).touch(); time.sleep(60)"
    process=subprocess.Popen([sys.executable,str(WRITER),sys.executable,'-c',child,str(marker)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        deadline=time.monotonic()+5
        while not marker.exists() and time.monotonic()<deadline: time.sleep(.02)
        assert marker.exists()
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5)==23
    finally:
        if process.poll() is None: process.kill(); process.wait()

def test_signal_exit_status_and_symlink_rejection(tmp_path):
    env=dict(os.environ,RUNTIME_LOG_DIR=str(tmp_path))
    result=subprocess.run([sys.executable,str(WRITER),sys.executable,'-c','import os,signal; os.kill(os.getpid(),signal.SIGTERM)'],env=env,capture_output=True,timeout=5)
    assert result.returncode==-signal.SIGTERM
    (tmp_path/'events.jsonl').unlink()
    target=tmp_path/'do-not-write';target.write_text('unchanged')
    (tmp_path/'events.jsonl').symlink_to(target)
    result=subprocess.run([sys.executable,str(WRITER),sys.executable,'-c','pass'],env=env,capture_output=True,timeout=5)
    assert result.returncode!=0 and target.read_text()=='unchanged'


def test_invalid_rotation_config_fails_before_child_start(tmp_path):
    marker=tmp_path/'must-not-run'
    env=dict(os.environ,RUNTIME_LOG_DIR=str(tmp_path),RUNTIME_LOG_MAX_BYTES='1')
    result=subprocess.run([sys.executable,str(WRITER),sys.executable,'-c',f'from pathlib import Path; Path({str(marker)!r}).touch()'],env=env,capture_output=True,timeout=5)
    assert result.returncode!=0 and not marker.exists()


def test_explicit_plugin_metadata_is_retained_but_unknown_fields_are_dropped(tmp_path):
    event={"action":"model_dispatch","event_kind":"instant","session_id":"ses_a",
           "message_id":"msg_"+"a"*32,"logical_model":"provider/model",
           "trace_id":"a"*32,"span_id":"b"*16,"prompt":"PRIVATE","api_key":"SECRET"}
    line='@@OPENCODE_CLOUD_EVENT@@'+json.dumps(event)
    env=dict(os.environ,RUNTIME_LOG_DIR=str(tmp_path),SANDBOX_ID='sbx_test')
    child=f'print({line!r})'
    result=subprocess.run([sys.executable,str(WRITER),sys.executable,'-c',child],env=env,capture_output=True,text=True,timeout=5)
    assert result.returncode==0
    records=[json.loads(line) for line in (tmp_path/'events.jsonl').read_text().splitlines()]
    retained=next(record for record in records if record['action']=='model_dispatch')
    assert retained['trace_id']=='a'*32 and retained['span_id']=='b'*16
    assert retained['session_id']=='ses_a' and retained['event_kind']=='instant'
    assert 'prompt' not in retained and 'api_key' not in retained
    assert 'PRIVATE' not in result.stdout and 'SECRET' not in result.stdout


def test_tool_marker_only_retains_valid_timing_and_identity():
    import importlib.util
    spec=importlib.util.spec_from_file_location('runtime_log_tool_test',WRITER)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    event={'action':'tool_error','trace_id':'a'*32,'span_id':'b'*16,'session_id':'ses_a','message_id':'msg_a','part_id':'prt_a','call_id':'call_a','tool':'bash','start_time_ms':100,'end_time_ms':150,'duration_ms':999,'output':'PRIVATE','input':{'key':'SECRET'},'error_code':'SECRET'}
    encode=lambda:module.PLUGIN_EVENT_PREFIX+json.dumps(event).encode()
    result=module.plugin_event(encode())
    assert result['duration_ms']==50 and result['error_code']=='ToolExecutionError'
    assert result['event_kind']=='span' and result['action']=='tool_error'
    assert 'SECRET' not in json.dumps(result) and 'PRIVATE' not in json.dumps(result)
    event['end_time_ms']=99;assert module.plugin_event(encode()) is None
    event['end_time_ms']=None;assert module.plugin_event(encode()) is None


def test_runtime_scope_preserves_source_end_time_without_prompt_text():
    import importlib.util
    spec=importlib.util.spec_from_file_location('runtime_scope_test',WRITER)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    item={'action':'runtime_complete','span_id':'b'*16,'session_id':'ses_a','message_id':'msg_a',
          'start_time_ms':1000,'end_time_ms':5000,'text':'PRIVATE'}
    result=module.plugin_event(module.PLUGIN_EVENT_PREFIX+json.dumps(item).encode())
    assert result['duration_ms']==4000 and result['timestamp'].endswith('00:00:05+00:00')
    assert 'PRIVATE' not in json.dumps(result)
