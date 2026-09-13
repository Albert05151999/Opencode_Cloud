#!/usr/bin/env python3
"""Deterministic OpenAI chat protocol stub. No paid model or intelligence claim."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import uuid

STATE={'requests':0,'stream_requests':0,'tool_calls':0,'tool_results':0,'load_responses':0,'tools_offered':[]}
LOCK=threading.Lock()
COMMAND='python3 -c "print(sum(range(1, 101)))"'

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        if self.path in ('/health','/evidence'):
            with LOCK: body=json.dumps({'protocol_stub':True,**STATE}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
        else:self.send_error(404)
    def do_POST(self):
        if self.path not in ('/v1/chat/completions','/chat/completions'):self.send_error(404);return
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
        messages=body.get('messages',[])
        latest_user=next((str(m.get('content','')) for m in reversed(messages) if m.get('role')=='user'),'')
        tools=[item.get('function',{}).get('name','') for item in body.get('tools',[])]
        last_user_index=max((i for i,m in enumerate(messages) if m.get('role')=='user'),default=-1)
        tool_result=any(m.get('role')=='tool' and '5050' in str(m.get('content','')) for m in messages[last_user_index+1:])
        load='LOAD-TEST-OK' in latest_user
        call_name=next((name for name in tools if name in ('bash','shell','execute','terminal')),None)
        with LOCK:
            STATE['requests']+=1;STATE['stream_requests']+=bool(body.get('stream'));STATE['tools_offered']=sorted(set(STATE['tools_offered']+tools))
            if tool_result:STATE['tool_results']+=1
            if load:STATE['load_responses']+=1
        if load: message={'role':'assistant','content':'LOAD-TEST-OK'};finish='stop'
        elif tool_result:message={'role':'assistant','content':'Python executed sum(range(1,101)); result: 5050.'};finish='stop'
        elif call_name:
            with LOCK:STATE['tool_calls']+=1
            message={'role':'assistant','content':None,'tool_calls':[{'id':'call_'+uuid.uuid4().hex[:12],'type':'function','function':{'name':call_name,'arguments':json.dumps({'command':COMMAND,'description':'Compute sum 1 through 100 using Python','timeout':10000})}}]};finish='tool_calls'
        else:message={'role':'assistant','content':'STUB_ERROR: expected a shell tool to perform the requested calculation.'};finish='stop'
        ident='chatcmpl-'+uuid.uuid4().hex
        common={'id':ident,'created':int(time.time()),'model':body.get('model','protocol-stub')}
        if body.get('stream'):
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-cache');self.end_headers()
            delta={key:value for key,value in message.items() if value is not None}
            if 'tool_calls' in delta:delta['tool_calls']=[dict(index=index,**call) for index,call in enumerate(delta['tool_calls'])]
            chunks=[{**common,'object':'chat.completion.chunk','choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                    {**common,'object':'chat.completion.chunk','choices':[{'index':0,'delta':{},'finish_reason':finish}],'usage':{'prompt_tokens':20,'completion_tokens':20,'total_tokens':40}}]
            try:
                for chunk in chunks:self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode());self.wfile.flush()
                self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
            except (BrokenPipeError,ConnectionResetError):pass
        else:
            result={**common,'object':'chat.completion','choices':[{'index':0,'message':message,'finish_reason':finish}],'usage':{'prompt_tokens':20,'completion_tokens':20,'total_tokens':40}}
            data=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=19090)
    args=p.parse_args();print(json.dumps({'listening':f'{args.host}:{args.port}','protocol_stub':True}),flush=True)
    ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()
