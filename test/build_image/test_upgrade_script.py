import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]

def release(tmp_path):
    for name in ('upgrade-module.sh','compose.sh'):
        shutil.copy2(ROOT/'build_image/bundle'/name,tmp_path/name)
    binary=tmp_path/'bin';binary.mkdir()
    docker=binary/'docker'
    docker.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$DOCKER_CALLS"
if [ "$1 $2" = "image inspect" ] && [ "${FAIL_INSPECT:-0}" = 1 ]; then exit 1; fi
exit 0
''');docker.chmod(0o755)
    env=dict(os.environ,PATH=str(binary)+os.pathsep+os.environ['PATH'],DOCKER_CALLS=str(tmp_path/'calls'))
    return env

def test_runtime_upgrade_changes_both_consumers_without_direct_container_stop(tmp_path):
    env=release(tmp_path)
    result=subprocess.run(['sh',str(tmp_path/'upgrade-module.sh'),'agent_runtime','opencode-cloud/agent_runtime:1.0.1','runtime.tar'],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    override=json.loads((tmp_path/'image-override-agent_runtime.json').read_text())
    assert set(override['services'])=={'catalog_service','sandbox_manager'}
    assert all(item['environment']['AGENT_RUNTIME_IMAGE']=='opencode-cloud/agent_runtime:1.0.1' for item in override['services'].values())
    calls=(tmp_path/'calls').read_text().splitlines()
    assert calls[0]=='load -i runtime.tar' and calls[1]=='image inspect opencode-cloud/agent_runtime:1.0.1'
    assert calls[2].endswith('up -d --no-deps --wait catalog_service sandbox_manager')
    assert 'not forcibly stopped' in result.stdout

def test_missing_loaded_tag_does_not_overwrite_existing_selection(tmp_path):
    env=release(tmp_path);env['FAIL_INSPECT']='1'
    path=tmp_path/'image-override-operations.json';path.write_text('preserve')
    result=subprocess.run(['sh',str(tmp_path/'upgrade-module.sh'),'operations','opencode-cloud/operations:missing','wrong.tar'],env=env,capture_output=True)
    assert result.returncode!=0 and path.read_text()=='preserve'
    assert 'compose' not in (tmp_path/'calls').read_text()

def test_regular_module_checks_image_before_restart(tmp_path):
    env=release(tmp_path)
    subprocess.run(['sh',str(tmp_path/'upgrade-module.sh'),'operations','opencode-cloud/operations:1.0.1','operations.tar'],env=env,check=True)
    assert json.loads((tmp_path/'image-override-operations.json').read_text())['services']['operations']['image']=='opencode-cloud/operations:1.0.1'
    assert (tmp_path/'calls').read_text().splitlines()[1].startswith('image inspect ')
