#!/usr/bin/env python3
"""Real local Ubuntu service flow driven through public HTTP; explicit protocol-stub or real-provider model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid
import re
from urllib.parse import urlsplit
import httpx

TERMINAL={'succeeded','failed','cancelled','interrupted','needs_recovery'}

class Acceptance:
    def __init__(self,url,token,model_url,output,stub_evidence_url=None,keep_resources=False,model_mode="stub",model_name="protocol-stub",model_key="local-stub-no-secret",skip_load=False):
        self.client=httpx.Client(base_url=url,headers={'Authorization':'Bearer '+token},timeout=180,trust_env=False)
        self.model_mode=model_mode;self.model_name=model_name;self.model_key=model_key;self.skip_load=skip_load
        self.model_url=model_url;self.output=Path(output);self.stub_evidence_url=stub_evidence_url;self.keep_resources=keep_resources
        self.run_id='accept-'+uuid.uuid4().hex[:10];self.agent_id=self.run_id;self.model_id=self.run_id
        self.client.headers['X-Cloud-Request-ID']=self.run_id
        self.report={'run_id':self.run_id,'api_base_url':url,'model_evidence':('real provider via supplied model configuration' if model_mode=='real' else 'deterministic OpenAI protocol stub, not a paid model'),'upstream_model':model_name,'steps':[],'result':'running'}
    def save(self):
        self.output.parent.mkdir(parents=True,exist_ok=True);self.output.write_text(json.dumps(self.report,indent=2)+'\n')
    def step(self,name,**evidence):
        self.report['steps'].append({'name':name,'passed':True,**evidence});self.save()
    def request(self,method,path,**kwargs):
        response=self.client.request(method,path,**kwargs)
        if response.is_error:raise RuntimeError(f'{method} {path} returned {response.status_code}')
        return response
    def json(self,method,path,**kwargs):return self.request(method,path,**kwargs).json()
    def poll_job(self,result):
        jid=result.get('id') or result.get('job_id') or result.get('job',{}).get('id')
        if not jid:raise RuntimeError('No operation job ID in response')
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            job=self.json('GET','/cloud/admin/jobs/'+jid)
            if job['status'] in TERMINAL:
                if job['status']!='succeeded':raise RuntimeError('Operation '+jid+' ended with status '+job['status'])
                return job
            time.sleep(.5)
        raise TimeoutError('Operation timed out: '+jid)
    def run(self):
        try:
            self.json('GET','/cloud/health');self.step('gateway.liveness')
            models=self.json('GET','/cloud/admin/models')
            legacy=[model for model in models['models'] if model.get('legacy') or model.get('provider')=='legacy'] if self.model_mode=='stub' else []
            fixture_models=[{'id':model['id'],'name':model.get('name') or model['id'],'provider':'openai-compatible','upstream_model':'protocol-stub','base_url':self.model_url,'api_key':'local-stub-no-secret','enabled':True,'legacy':False,'context':32000,'output':2048} for model in legacy]
            fixture_models.append({'id':self.model_id,'name':'Acceptance model','provider':'openai-compatible','upstream_model':self.model_name,'base_url':self.model_url,'api_key':self.model_key,'enabled':True,'context':32000,'output':2048})
            self.json('POST','/cloud/admin/models/import',json={'revision':models['revision'],'replace':self.model_mode=='stub','models':fixture_models})
            self.step('first_install.configure_default_models',replaced_legacy_ids=[model['id'] for model in legacy],catalog_revision=models['revision'],default_agents_and_resources_preserved=True)
            job=self.poll_job(self.json('POST','/cloud/admin/models/apply',json={'request_id':self.run_id+'-models'}));self.model_job_id=job['id'];self.step('models.import_publish',job_id=job['id'])
            config={'name':'Local acceptance Agent','instructions':'Use the bash tool to execute the requested Python calculation. Do not invent tool results.','allowed_model_ids':[self.model_id],'default_model_id':self.model_id,'enabled':True}
            self.json('PUT','/cloud/admin/agents/'+self.agent_id,json={'config':config})
            job=self.poll_job(self.json('POST',f'/cloud/admin/agents/{self.agent_id}/apply',json={'request_id':self.run_id+'-agent'}));self.step('agent.publish',job_id=job['id'])
            native={'x-cloud-agent-id':self.agent_id,'x-cloud-username':'acceptance-user'}
            session=self.json('POST','/session',headers=native,json={'title':'Real provider tool acceptance' if self.model_mode=='real' else 'Local protocol tool acceptance'})
            sid=session['id'];self.report['session_id']=sid;self.step('opencode.session',session_id=sid)
            observed=[];stop=threading.Event();connected=threading.Event()
            def consume():
                try:
                    with self.client.stream('GET','/event',headers={**native,'x-cloud-session-id':sid},timeout=httpx.Timeout(180,read=30)) as stream:
                        stream.raise_for_status();connected.set()
                        for line in stream.iter_lines():
                            if line.startswith('data:'):
                                try:
                                    event=json.loads(line[5:]);payload=event.get('payload',event);observed.append(payload.get('type','unknown'))
                                except ValueError:pass
                            if stop.is_set():break
                except (httpx.HTTPError,RuntimeError):pass
            thread=threading.Thread(target=consume,daemon=True);thread.start();assert connected.wait(30),'SSE did not connect'
            started=time.monotonic()
            answer=self.json('POST',f'/session/{sid}/message',headers=native,json={'parts':[{'type':'text','text':'Run Python in the bash tool: print(sum(range(1,101))). Report the actual result.'}]})
            elapsed=time.monotonic()-started;stop.set();thread.join(3)
            messages=self.json('GET',f'/session/{sid}/message',headers=native)
            serialized=json.dumps(messages)
            assert '5050' in serialized,'Expected actual tool result missing'
            tool_parts=[part for message in messages for part in message.get('parts',[]) if part.get('type')=='tool']
            assert any('5050' in json.dumps(part) and part.get('state',{}).get('status')=='completed' for part in tool_parts),'No completed OpenCode tool with5050'
            assert any(event.startswith('message.') for event in observed),'SSE did not observe message events'
            self.step('opencode.python_tool_sse',elapsed_seconds=round(elapsed,3),completed_tools=len(tool_parts),tool_names=sorted({part.get('tool','unknown') for part in tool_parts}),command='python3 -c print(sum(range(1,101)))',sse_event_types=sorted(set(observed)),result='5050')
            content=b'OpenCode independent service file acceptance\n'
            uploaded=self.json('POST','/cloud/files/upload',data={'agent_id':self.agent_id,'username':'acceptance-user','session_id':sid,'relative_path':'acceptance.txt'},files={'file':('acceptance.txt',content,'text/plain')})
            downloaded=self.request('GET','/cloud/files/download',params={'agent_id':self.agent_id,'username':'acceptance-user','session_id':sid,'path':'acceptance.txt'})
            assert downloaded.content==content;self.step('files.roundtrip',sha256=hashlib.sha256(content).hexdigest(),bytes=len(content))
            sandboxes=self.json('GET','/cloud/admin/sandboxes',params={'q':self.agent_id})
            row=next(item for item in sandboxes.get('items',[]) if item.get('agent_id')==self.agent_id)
            sandbox_id=row.get('sandbox_id',row.get('id'));self.report['sandbox_id']=sandbox_id
            for action in ('stop','start'):
                job=self.poll_job(self.json('POST',f'/cloud/admin/sandboxes/{sandbox_id}/{action}',json={'request_id':self.run_id+'-'+action}))
                self.step('sandbox.'+action,job_id=job['id'])
            logs=self.json('GET','/cloud/logs',params={'module':'operations','job_id':self.model_job_id,'limit':100})
            trace=next((item.get('trace_id') for item in logs['items'] if item.get('trace_id')),None);assert trace,'Publish job trace missing'
            trace_result=self.json('GET','/cloud/traces/'+trace);assert trace_result.get('events');trace_modules=sorted({event.get('module') for event in trace_result['events'] if event.get('module')});assert 'operations' in trace_modules and len(trace_modules)>=2,'Expected correlated cross-service trace';self.step('logs.trace',trace_id=trace,event_count=len(trace_result['events']),modules=trace_modules)
            if not self.skip_load:
                load=self.json('POST','/cloud/admin/load-tests',json={'request_id':self.run_id+'-load','agents':[{'agent_id':self.agent_id,'users':1,'cpu_limit':1,'memory_mb':1024}],'timeout_seconds':120,'prepare_timeout_seconds':120})
                rid=load.get('id') or load.get('run_id');assert rid,'Missing load run ID';deadline=time.monotonic()+240
                while time.monotonic()<deadline:
                    status=self.json('GET','/cloud/admin/load-tests/'+rid)
                    if status['status'] not in {'queued','preparing','running','cancelling'}:break
                    time.sleep(1)
                assert status['status']=='completed' and all(user['phase']=='succeeded' for user in status['users']),'Load test did not succeed'
                self.step('load_test',run_id=rid,status=status['status'],users=len(status['users']))
                self.json('POST',f'/cloud/admin/load-tests/{rid}/cleanup',json={'confirmation':rid})
                deadline=time.monotonic()+120
                while time.monotonic()<deadline:
                    cleanup=self.json('GET','/cloud/admin/load-tests/'+rid)
                    if cleanup.get('cleanup_status')=='cleaned':break
                    if cleanup.get('cleanup_error'):raise RuntimeError('Load cleanup failed; inspect operation with authorized API')
                    time.sleep(.5)
                assert cleanup.get('cleanup_status')=='cleaned','Load cleanup timed out'
                self.step('load_test.cleanup',run_id=rid)
            else:
                self.step('load_test.skipped',reason='Explicit secondary-provider basic-chain run')
            if self.keep_resources:
                self.step('resources.retained',agent_id=self.agent_id,sandbox_id=sandbox_id,session_id=sid)
            if self.stub_evidence_url:
                evidence=httpx.get(self.stub_evidence_url,trust_env=False,timeout=10).json();assert evidence['tool_results']>=1 and evidence['stream_requests']>=1
                self.report['protocol_stub_evidence']=evidence
            self.report['result']='passed'
        except Exception as error:
            self.report['result']='failed';self.report['failure']='Acceptance failed ('+type(error).__name__+'); inspect the last completed step and authorized service logs';raise RuntimeError(self.report['failure']) from None
        finally:self.save();self.client.close()
        return self.report

def read_model_env(path):
    values={}
    if path:
        for line in Path(path).read_text().splitlines():
            line=line.strip()
            if not line or line.startswith('#'):continue
            if line.startswith('export '):line=line[7:].lstrip()
            key,sep,value=line.partition('=')
            if not sep or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',key.strip()):raise ValueError('Invalid env file syntax')
            value=value.strip()
            if value.startswith(('"', "'")):
                if len(value)<2 or value[-1]!=value[0]:raise ValueError('Invalid quoted env value')
                value=value[1:-1]
            else:value=re.split(r'\s+#',value,maxsplit=1)[0].rstrip()
            values[key.strip()]=value
    values.update(os.environ)
    return values


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-base-url',default=os.environ.get('API_BASE_URL'))
    parser.add_argument('--model-mode',choices=['stub','real'],default='stub')
    parser.add_argument('--env-file',help='explicit dotenv containing SEED_MODEL_BASE_URL/NAME/API_KEY and optional ADMIN_TOKEN')
    parser.add_argument('--model-base-url',help='explicit model endpoint override')
    parser.add_argument('--stub-evidence-url',default=os.environ.get('STUB_EVIDENCE_URL'))
    parser.add_argument('--keep-resources',action='store_true',help='retain main Agent/session/sandbox for later checks; disposable load fixtures are always cleaned')
    parser.add_argument('--skip-load',action='store_true',help='explicitly skip load only for a secondary-provider basic-chain run')
    parser.add_argument('--validate-only',action='store_true',help='validate inputs without HTTP calls or printing credentials')
    parser.add_argument('--output',default='artifacts/verification/server-acceptance.json')
    args=parser.parse_args()
    try:values=read_model_env(args.env_file)
    except (ValueError,OSError):parser.error('Cannot parse explicit env file')
    token=values.get('ADMIN_TOKEN')
    model_url=args.model_base_url or values.get('SEED_MODEL_BASE_URL' if args.model_mode=='real' else 'STUB_MODEL_BASE_URL')
    name=values.get('SEED_MODEL_NAME') if args.model_mode=='real' else 'protocol-stub'
    key=values.get('SEED_MODEL_API_KEY') if args.model_mode=='real' else 'local-stub-no-secret'
    if not all((args.api_base_url,token,model_url,name,key)):parser.error('Missing API address, authentication, or model configuration')
    for url in (args.api_base_url,model_url):
        try:parsed=urlsplit(url)
        except ValueError:parser.error('Invalid endpoint')
        if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:parser.error('Endpoints must be HTTP(S) without credentials/query/fragment')
    if args.model_mode=='real' and name.startswith('openai/'):parser.error('SEED_MODEL_NAME must omit LiteLLM openai/ prefix')
    if args.validate_only:
        print(json.dumps({'configuration_valid':True,'model_mode':args.model_mode}));return
    report=Acceptance(args.api_base_url,token,model_url,args.output,args.stub_evidence_url if args.model_mode=='stub' else None,args.keep_resources,args.model_mode,name,key,args.skip_load).run()
    print(json.dumps({'result':report['result'],'run_id':report['run_id'],'report':args.output}))

if __name__=='__main__':main()
