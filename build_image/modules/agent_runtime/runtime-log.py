#!/usr/bin/env python3
"""Bounded metadata-only runtime output supervisor; never persists child text."""
import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import selectors
import re
import time
import signal
import subprocess
import sys

PLUGIN_EVENT_PREFIX=b'@@OPENCODE_CLOUD_EVENT@@'
SAFE_ID=re.compile(r'^[A-Za-z0-9_.:/-]{1,256}$')


def plugin_event(line):
    """Parse one explicit plugin record and retain metadata fields only."""
    if not line.startswith(PLUGIN_EVENT_PREFIX) or len(line) > 4096:
        return None
    try: value=json.loads(line[len(PLUGIN_EVENT_PREFIX):])
    except (UnicodeDecodeError,json.JSONDecodeError): return None
    if not isinstance(value,dict) or value.get('action') not in {'model_dispatch','tool_complete','tool_error','runtime_complete','runtime_error'}: return None
    action=value['action']
    result={'action':action,'event_kind':'instant' if action=='model_dispatch' else 'span'}
    for name in ('session_id','message_id','logical_model','part_id','call_id','tool'):
        item=value.get(name)
        if item is not None and isinstance(item,str) and SAFE_ID.fullmatch(item): result[name]=item
    trace_id=value.get('trace_id'); span_id=value.get('span_id')
    if isinstance(trace_id,str) and re.fullmatch(r'[0-9a-f]{32}',trace_id) and int(trace_id,16): result['trace_id']=trace_id
    if isinstance(span_id,str) and re.fullmatch(r'[0-9a-f]{16}',span_id) and int(span_id,16): result['span_id']=span_id
    parent=value.get('parent_span_id')
    if isinstance(parent,str) and re.fullmatch(r'[0-9a-f]{16}',parent) and int(parent,16): result['parent_span_id']=parent
    if action != 'model_dispatch':
        start,end=value.get('start_time_ms'),value.get('end_time_ms')
        if type(start) is not int or type(end) is not int or start < 0 or end > 253402300799999 or not 0 <= end-start <= 86400000: return None
        required=('span_id','session_id','message_id') if action.startswith('runtime_') else ('trace_id','span_id','session_id','message_id','part_id','call_id','tool')
        if not all(name in result for name in required): return None
        result.update(duration_ms=end-start,start_time_ms=start,end_time_ms=end)
        result['timestamp']=datetime.datetime.fromtimestamp(end/1000,datetime.timezone.utc).isoformat()
        if action=='tool_error': result['error_code']='ToolExecutionError'
        if action=='runtime_error': result['error_code']='RuntimeExecutionError'
    return result


def supervise(command, root, sandbox_id, max_bytes=10485760, backup_count=5):
    sandbox_id = sandbox_id if re.fullmatch(r'[A-Za-z0-9_-]{1,128}',sandbox_id) else 'unknown'
    root = Path(root)
    if max_bytes < 1024 or not 1 <= backup_count <= 20: raise ValueError('Invalid runtime log rotation limits')
    root.mkdir(parents=True,exist_ok=True)
    if root.is_symlink(): raise ValueError('Runtime log directory cannot be a symlink')
    target = root / 'events.jsonl'
    if target.is_symlink(): raise ValueError('Runtime log file cannot be a symlink')
    for index in range(1,backup_count+1):
        if (root / f'events.jsonl.{index}').is_symlink(): raise ValueError('Runtime rotated log cannot be a symlink')
    logger = logging.Logger('runtime-metadata'); logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(target,maxBytes=max_bytes,backupCount=backup_count,encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(message)s')); logger.addHandler(handler)
    os.chmod(target,0o644)
    def emit(action, **fields):
        event={'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'level':'INFO','module':'agent_runtime',
               'instance_id':sandbox_id,'sandbox_id':sandbox_id,'action':action, **fields}
        line=json.dumps(event,separators=(',',':'))
        logger.info(line)
        # stdout contains the same safe metadata, never raw OpenCode output.
        try: print(line,flush=True)
        except (BrokenPipeError,OSError): pass
    child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    previous={}
    termination_deadline=None
    def forward(signum,frame):
        nonlocal termination_deadline
        termination_deadline=time.monotonic()+10
        try: os.killpg(child.pid,signum)
        except ProcessLookupError: pass
    for signum in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
        previous[signum]=signal.signal(signum,forward)
    emit('process.started')
    poll=selectors.DefaultSelector()
    buffers={'stdout':b'','stderr':b''}
    for name,stream in (('stdout',child.stdout),('stderr',child.stderr)):
        poll.register(stream,selectors.EVENT_READ,name)
    try:
        while poll.get_map():
            if child.poll() is not None or (termination_deadline is not None and time.monotonic()>termination_deadline):
                try: os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError: pass
            for key,_ in poll.select(timeout=.2):
                content=os.read(key.fileobj.fileno(),4096)
                if not content:
                    poll.unregister(key.fileobj); key.fileobj.close()
                else:
                    # Arbitrary output may contain prompts, credentials or multiline payloads.
                    # Retain bounded stream/size diagnostics only; no heuristic redaction leaks.
                    emit('output.redacted',stream=key.data,bytes=len(content),content_retained=False)
                    if key.data == 'stdout':
                        buffered=(buffers['stdout']+content)[-8192:]
                        lines=buffered.split(b'\n')
                        buffers['stdout']=lines.pop()
                        for line in lines:
                            fields=plugin_event(line)
                            if fields is not None: emit(fields.pop('action'),**fields)
        code=child.wait(); emit('process.exited',exit_code=code)
        return code
    finally:
        poll.close()
        if child.poll() is None:
            os.killpg(child.pid,signal.SIGKILL); child.wait()
        for signum,old in previous.items(): signal.signal(signum,old)
        handler.close()


def main():
    code=supervise(sys.argv[1:] or ['/usr/local/bin/runtime-entrypoint'],os.environ.get('RUNTIME_LOG_DIR','/runtime-log'),
                   os.environ.get('SANDBOX_ID','standalone'),int(os.environ.get('RUNTIME_LOG_MAX_BYTES','10485760')),
                   int(os.environ.get('RUNTIME_LOG_BACKUP_COUNT','5')))
    if code<0:
        signal.signal(-code,signal.SIG_DFL); os.kill(os.getpid(),-code)
    raise SystemExit(code)

if __name__=='__main__': main()
