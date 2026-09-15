import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import threading
import pytest

from build_image.build import ROOT, include_seed_tools


def prepare_release(tmp_path):
    source=tmp_path/'source';shutil.copytree(ROOT/'config',source/'config')
    # Local credentials and arbitrary user seed files must never enter the release.
    (source/'config/catalog_service/.env').write_text('ADMIN_TOKEN=DO_NOT_PACKAGE\n')
    (source/'config/catalog_service/seeds/private.json').write_text('{"secret":"DO_NOT_PACKAGE"}')
    release=tmp_path/'release with spaces';include_seed_tools(source,release)
    shutil.copy2(ROOT/'build_image/bundle/import-models.sh',release/'import-models.sh')
    shutil.rmtree(source)
    return release


def test_extracted_release_dry_run_needs_no_source_or_real_env(tmp_path):
    release=prepare_release(tmp_path)
    env=dict(os.environ,SEED_PYTHON=sys.executable)
    result=subprocess.run(['sh',str(release/'import-models.sh')],cwd=tmp_path,env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout)
    assert report['mode']=='dry-run' and not report['published']
    assert not (release/'config/catalog_service/.env').exists()
    assert not (release/'config/catalog_service/seeds/private.json').exists()
    assert all(b'DO_NOT_PACKAGE' not in path.read_bytes() for path in release.rglob('*') if path.is_file())


@pytest.mark.parametrize('env_location', ['config/catalog_service/.env', '.env'])
def test_release_wrapper_passes_apply_revision_replace_and_local_credentials(tmp_path, env_location):
    release=prepare_release(tmp_path)
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            received.append((self.path,self.headers['Authorization'],json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"ok":true}')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    env={key:value for key,value in os.environ.items() if key!='ADMIN_TOKEN' and not key.startswith('SEED_MODEL_')}
    env.update(SEED_PYTHON=sys.executable,API_BASE_URL=f'http://127.0.0.1:{server.server_port}')
    (release/env_location).write_text('ADMIN_TOKEN=local-admin\nSEED_MODEL_API_KEY=local-upstream\nSEED_MODEL_NAME=local-model\nSEED_MODEL_BASE_URL=http://127.0.0.1:19090/v1\n')
    if env_location != '.env':
        (release/'.env').write_text('ADMIN_TOKEN=compose-admin\n')
    try:
        result=subprocess.run(['sh',str(release/'import-models.sh'),'--apply','--revision','7','--replace'],cwd=tmp_path,env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        assert received[0][0]=='/cloud/admin/models/import'
        assert received[0][1]=='Bearer local-admin'
        assert received[0][2]['revision']==7 and received[0][2]['replace'] is True
        assert received[0][2]['models'][0]['api_key']=='local-upstream'
        assert 'local-upstream' not in result.stdout and 'local-admin' not in result.stdout
    finally:server.shutdown();server.server_close()


def test_exported_script_alone_has_actionable_error(tmp_path):
    script=tmp_path/'import-models.sh';shutil.copy2(ROOT/'build_image/bundle/import-models.sh',script)
    result=subprocess.run(['sh',str(script)],capture_output=True,text=True)
    assert result.returncode!=0 and 'complete extracted release' in result.stderr
