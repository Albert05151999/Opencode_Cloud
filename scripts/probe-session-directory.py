"""Probe pinned native directory routing without any model request."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import urllib.parse

with tempfile.TemporaryDirectory(prefix='cloud-directory-probe-') as tmp:
    root = Path(tmp)
    env = os.environ.copy()
    for key in ('HOME', 'XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
        env[key] = str(root / key)
        Path(env[key]).mkdir()
    env['OPENCODE_CONFIG_CONTENT'] = json.dumps({'share':'disabled','autoupdate':False,'plugin':[]})
    with (root/'log').open('w') as log:
        p = subprocess.Popen(['opencode','serve','--hostname','127.0.0.1','--port','18496'],cwd=root,env=env,stdout=log,stderr=log)
        def api(method,path,body=None,directory=None):
            if directory:path+='?'+urllib.parse.urlencode({'directory':str(directory)})
            req=urllib.request.Request('http://127.0.0.1:18496'+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=30) as r:
                raw=r.read();return json.loads(raw) if raw else None
        try:
            for _ in range(100):
                try:
                    api('GET','/global/health');break
                except OSError:time.sleep(.2)
            a=root/'a';b=root/'b';a.mkdir();b.mkdir()
            s=api('POST','/session',{},a)
            api('POST','/experimental/control-plane/move-session',{'sessionID':s['id'],'destination':{'directory':str(b)},'moveChanges':False})
            result=api('POST',f'/session/{s["id"]}/shell',{'agent':'build','command':'pwd'},b)
            print(json.dumps({'created':s,'shell_in_b':result,'list_root':api('GET','/session',directory=root),'list_b':api('GET','/session',directory=b)},indent=2))
        finally:
            p.terminate()
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait()
