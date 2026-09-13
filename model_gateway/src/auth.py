"""Runtime credentials authorize only the inference data plane."""

import secrets


class RuntimeCredentialMiddleware:
    def __init__(self, app, runtime_token, service_token):
        self.app = app
        self.runtime_token = runtime_token
        self.service_token = service_token

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] == "http"
            and scope["path"].startswith("/v1/")
            and self.runtime_token
        ):
            headers = list(scope.get("headers", []))
            supplied = dict(headers).get(b"authorization", b"").decode("latin1")
            if secrets.compare_digest(supplied, "Bearer " + self.runtime_token):
                scope = dict(scope)
                scope["headers"] = [
                    (key, value) for key, value in headers if key != b"authorization"
                ] + [(b"authorization", ("Bearer " + self.service_token).encode())]
        await self.app(scope, receive, send)
