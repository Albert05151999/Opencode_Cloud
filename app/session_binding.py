"""Bind native sessions to their persistent file scope before execution."""
import asyncio
from weakref import WeakValueDictionary

from fastapi import HTTPException
import httpx

from app.workspace import validate_identifier


async def directory_collection(client, registry, endpoint, path='/session/status', timeout=5):
    """Native status/permission collections are scoped to an OpenCode directory."""
    routes = await asyncio.to_thread(registry.list_sessions_for_sandbox, endpoint.sandbox_id)
    directories = ['/workspace', *[f'/workspace/sessions/{r.session_id}' for r in routes]]
    semaphore = asyncio.Semaphore(8)
    async def get(directory):
        async with semaphore:
            response = await client.get(endpoint.base_url + path, params={'directory': directory}, timeout=timeout)
            response.raise_for_status()
            return response.json()
    groups = await asyncio.gather(*(get(d) for d in dict.fromkeys(directories)))
    if path == '/session/status':
        result = {}
        for group in groups:
            for sid, status in group.items():
                if result.get(sid, {}).get('type') not in {'busy', 'retry'}:
                    result[sid] = status
        return result
    return list({item['id']: item for group in groups for item in group}.values())


class SessionBindings:
    def __init__(self, registry, workspaces, client):
        self.registry, self.workspaces, self.client = registry, workspaces, client
        self.locks = WeakValueDictionary()

    async def ensure(self, endpoint, route):
        sid = validate_identifier(route.session_id, 'session_id')
        # Old metadata accepted arbitrary labels, but the public file API has
        # always used sessions/<id>. That same directory is authoritative here.
        directory = f'/workspace/sessions/{sid}'
        lock = self.locks.setdefault(sid, asyncio.Lock())
        async with lock:
            await asyncio.to_thread(self.workspaces.user_scope, route.agent_id, route.username, sid)
            for name in ('inputs', 'outputs'):
                await asyncio.to_thread(self.workspaces.resolve_user_path,
                    route.agent_id, route.username, name + '/.placeholder', sid)
            try:
                response = await self.client.get(endpoint.base_url + f'/session/{sid}')
                if response.status_code == 404:
                    raise HTTPException(404, 'Native session no longer exists')
                response.raise_for_status()
                session = response.json()
                if session.get('directory') != directory:
                    moved = await self.client.post(endpoint.base_url + '/experimental/control-plane/move-session',
                        json={'sessionID': sid, 'destination': {'directory': directory}, 'moveChanges': False})
                    if moved.status_code >= 400:
                        # Native move rejects busy sessions; never stop them or
                        # silently fall back to executing in the shared root.
                        raise HTTPException(409, 'Session directory binding failed; wait for active tasks to finish and retry')
                    response = await self.client.get(endpoint.base_url + f'/session/{sid}')
                    response.raise_for_status()
                    session = response.json()
                    if session.get('directory') != directory:
                        raise HTTPException(502, 'Native session directory binding was not confirmed')
                return session
            except (httpx.HTTPError, ValueError) as exc:
                raise HTTPException(502, 'Unable to verify native session directory') from exc


async def flattened_events(upstream):
    """Keep /event's native payload contract while subscribing across directories."""
    import json
    data = []
    size = 0
    async for line in upstream.aiter_lines():
        if line == '':
            if data:
                event = json.loads('\n'.join(data))
                payload = event.get('payload', event)
                yield ('data: ' + json.dumps(payload, separators=(',', ':')) + '\n\n').encode()
            data, size = [], 0
        elif line.startswith('data:'):
            size += len(line)
            if size > 2 * 1024 * 1024:
                raise ValueError('Native SSE frame exceeds limit')
            data.append(line[5:].lstrip(' '))
        elif line.startswith(':'):
            yield (line + '\n\n').encode()
