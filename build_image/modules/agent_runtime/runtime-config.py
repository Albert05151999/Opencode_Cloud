#!/usr/bin/env python3
"""Translate rendered runtime deployment fields to OpenCode's environment contract."""
import json
import os
from pathlib import Path


config = json.loads(Path(os.environ.get('MODULE_CONFIG','/config/config.json')).read_text())
if config['module_id'] != 'agent_runtime': raise ValueError('Wrong runtime module configuration')
os.environ.setdefault('OPENCODE_HOSTNAME',config['host'])
os.environ.setdefault('OPENCODE_PORT',str(config['port']))
values=config.get('settings',{})
os.environ.setdefault('RUNTIME_LOG_MAX_BYTES',str(values.get('log_max_bytes',10485760)))
os.environ.setdefault('RUNTIME_LOG_BACKUP_COUNT',str(values.get('log_backup_count',5)))
os.execv('/opt/venv/bin/python',['/opt/venv/bin/python','/usr/local/bin/runtime-log.py','/usr/local/bin/runtime-entrypoint'])
