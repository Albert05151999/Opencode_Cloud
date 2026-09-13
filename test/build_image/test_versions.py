import json
from pathlib import Path
import shutil
import pytest
import build_image.build as build


def version_root(tmp_path):
    for relative in ('config/build_image/versions.json','model_gateway/requirements.lock','agent_runtime/image/package.json','agent_runtime/image/package-lock.json','VERSION'):
        target=tmp_path/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(build.ROOT/relative,target)
    return tmp_path


def test_runtime_and_python_build_args_reach_docker(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(build,'run',lambda *args:calls.append(args))
    build.build_module('agent_runtime',artifacts=tmp_path)
    expected=build.version_arguments('agent_runtime')
    assert all(f'{key}={value}' in calls[0] for key,value in expected.items())
    assert 'NODE_ARCHIVE_SHA256' in expected and 'PYTHON_VERSION' in expected
    build.build_module('operations',artifacts=tmp_path)
    assert all(f'{key}={value}' in calls[1] for key,value in build.version_arguments('operations').items())

@pytest.mark.parametrize('key,module',[('OPENCODE_VERSION','agent_runtime'),('LITELLM_VERSION','model_gateway')])
def test_center_version_mismatch_fails_instead_of_ignoring(tmp_path,key,module):
    root=version_root(tmp_path)
    path=root/'config/build_image/versions.json';versions=json.loads(path.read_text());versions[key]='999.0.0';path.write_text(json.dumps(versions))
    with pytest.raises(ValueError,match='re-lock'):build.version_arguments(module,root)


def test_bundle_version_reads_root_file(tmp_path,monkeypatch):
    root=version_root(tmp_path/'root');(root/'VERSION').write_text('9.8.7\n')
    assert build.release_version(root)=='9.8.7'
    monkeypatch.setattr(build,'release_version',lambda root:'9.8.7')
    result=build.bundle(prepare_only=True,artifacts=tmp_path/'artifacts')
    assert result.name=='9.8.7' and json.loads((result/'manifest.json').read_text())['version']=='9.8.7'


def test_python_and_runtime_recipes_use_central_base_versions():
    runtime=(build.ROOT/'build_image/modules/agent_runtime/Dockerfile').read_text()
    assert 'FROM ${UBUNTU_IMAGE}' in runtime and 'FROM ${CONTROLLER_BASE_IMAGE}' in runtime
    assert 'Python ${PYTHON_VERSION}' in runtime
    assert 'PYTHON_VERSION' in (build.ROOT/'agent_runtime/image/smoke/image-smoke.sh').read_text()
    for module in build.MODULES[:-1]:
        assert 'FROM ${CONTROLLER_BASE_IMAGE}' in (build.ROOT/'build_image/modules'/module/'Dockerfile').read_text()
