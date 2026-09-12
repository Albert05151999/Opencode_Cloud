"""Report bounded upstream connectivity without printing keys or upstream bodies."""
import asyncio
import json
import sys
from pathlib import Path

import docker
import httpx


async def main():
    container = docker.from_env().containers.get('deploy-model-gateway-1')
    environment = dict(s.split('=',1) for s in container.attrs['Config']['Env'] if '=' in s)
    async def probe(prefix):
        async with httpx.AsyncClient(timeout=20,trust_env=False) as client:
            try:
                response = await client.post(environment[prefix+'_1_API_BASE']+'/chat/completions',
                    headers={'Authorization':'Bearer '+environment[prefix+'_API_KEY']},
                    json={'model':environment[prefix+'_MODEL'].split('/',1)[1],
                          'messages':[{'role':'user','content':'Reply OK'}],'max_tokens':32})
                return {'model':prefix,'status':response.status_code,'ok':response.is_success}
            except Exception as exc:
                return {'model':prefix,'ok':False,'error':type(exc).__name__}
    results = await asyncio.gather(probe('CODING_FAST'),probe('CODING_QUALITY'))
    async with httpx.AsyncClient(timeout=30,trust_env=False) as client:
        try:
            response = await client.post('http://127.0.0.1:4001/v1/chat/completions',json={'model':'coding-fast','messages':[{'role':'user','content':'Reply OK'}],'max_tokens':32})
            results.append({'model':'gateway/coding-fast','status':response.status_code,'ok':response.is_success})
        except Exception as exc:
            results.append({'model':'gateway/coding-fast','ok':False,'error':type(exc).__name__})
    print(json.dumps(results))


if __name__=='__main__':
    asyncio.run(main())
