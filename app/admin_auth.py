"""Single-administrator ASGI authentication without buffering SSE responses."""
import secrets

from starlette.responses import JSONResponse


class AdminAuthMiddleware:
    def __init__(self, app, token):
        self.app, self.token = app, token.encode()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        local_metrics = scope['path'] == '/metrics' and (scope.get('client') or ('',))[0] in {'127.0.0.1', '::1'}
        if scope['path'] != '/cloud/health' and not local_metrics:
            values = [v for k, v in scope['headers'] if k.lower() == b'authorization']
            supplied = values[0] if len(values) == 1 else b''
            if not secrets.compare_digest(supplied, b'Bearer ' + self.token):
                return await JSONResponse({'detail': 'Administrator credential required'}, 401,
                    headers={'WWW-Authenticate': 'Bearer'})(scope, receive, send)
        return await self.app(scope, receive, send)
