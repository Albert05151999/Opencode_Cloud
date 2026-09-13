"""Same-origin local UI, Windows credential storage and bounded remote proxy."""

import asyncio
import json
import os
import secrets
import re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Body, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from admin_web.local_service.importer import Importer
from admin_web.local_service.configuration import load
from admin_web.local_service.runtime import until_stopped


_TRACEPARENT = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-0[01]")
_CORRELATION_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}")


def _correlation_headers(headers):
    traceparent = headers.get("traceparent", "")
    match = _TRACEPARENT.fullmatch(traceparent)
    if not match or not int(match[1], 16) or not int(match[2], 16):
        traceparent = f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01"
    request_id = headers.get("x-cloud-request-id", "")
    if not _CORRELATION_ID.fullmatch(request_id):
        request_id = "req_" + secrets.token_hex(16)
    return {"traceparent": traceparent, "x-cloud-request-id": request_id}


class Connection:
    def __init__(self, root):
        self.path = root / "connection.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.url = load()["gateway_url"]
        self.token = ""
        if self.path.is_file():
            self.url = json.loads(self.path.read_text())["url"]
        try:
            if os.name == "nt":
                from keyring.backends.Windows import WinVaultKeyring

                self.token = (
                    WinVaultKeyring().get_password("opencode-cloud-web", self.url) or ""
                )
        except Exception:
            pass

    def save(self, url, token, remember):
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise HTTPException(
                400,
                "Enter an HTTP(S) server URL without credentials or query parameters",
            )
        self.url = url.rstrip("/")
        self.token = token
        if remember:
            if os.name != "nt":
                raise HTTPException(
                    400, "Credential persistence requires Windows Credential Manager"
                )
            try:
                from keyring.backends.Windows import WinVaultKeyring

                WinVaultKeyring().set_password("opencode-cloud-web", self.url, token)
            except Exception:
                raise HTTPException(
                    503,
                    "Windows Credential Manager unavailable; uncheck Remember to use this session only",
                )
        self.path.write_text(json.dumps({"url": self.url}), encoding="utf-8")


def create_local_app(root=None, connection=None):
    root = Path(root or load()["data_root"])
    connection = connection or Connection(root)
    importer = Importer()
    csrf = secrets.token_urlsafe(32)
    client = httpx.AsyncClient(
        trust_env=False, timeout=httpx.Timeout(120, connect=10), follow_redirects=False
    )

    @asynccontextmanager
    async def lifespan(app):
        yield
        await client.aclose()

    app = FastAPI(title="OpenCode local companion", lifespan=lifespan)
    app.state.connection = connection
    app.state.stopping = asyncio.Event()

    @app.middleware("http")
    async def protect(request, call_next):
        request.state.correlation = _correlation_headers(request.headers)
        if app.state.stopping.is_set():
            return JSONResponse({"detail": "Local service is shutting down"}, 503)
        host = request.headers.get("host", "")
        hostname = host.split(":")[0]
        origin = request.headers.get("origin")
        if hostname not in {"localhost", "127.0.0.1"}:
            return JSONResponse({"detail": "Localhost access only"}, 403)
        if origin and origin != "http://" + host:
            return JSONResponse({"detail": "Cross-origin access denied"}, 403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site access denied"}, 403)
        if request.method not in {
            "GET",
            "HEAD",
            "OPTIONS",
        } and not secrets.compare_digest(request.headers.get("x-local-csrf", ""), csrf):
            return JSONResponse(
                {"detail": "Local session token required; refresh the page"}, 403
            )
        response = await call_next(request)
        response.headers.setdefault(
            "traceparent", request.state.correlation["traceparent"]
        )
        response.headers.setdefault(
            "x-cloud-request-id", request.state.correlation["x-cloud-request-id"]
        )
        response.headers.setdefault(
            "x-cloud-trace-id", request.state.correlation["traceparent"].split("-")[1]
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = (
            "no-store"
            if request.url.path.startswith(("/local/", "/remote/"))
            else "no-cache"
        )
        return response

    @app.get("/local/bootstrap")
    def bootstrap():
        return {
            "csrf": csrf,
            "url": connection.url,
            "credential_configured": bool(connection.token),
            "encrypted": connection.url.startswith("https:"),
        }

    @app.put("/local/connection")
    def save_connection(payload: dict = Body()):
        token = payload.get("token")
        if token is None and payload["url"].rstrip("/") == connection.url:
            token = connection.token
        connection.save(payload["url"], token or "", payload.get("remember", False))
        return {"ok": True}

    async def remote_json(method, path, payload=None, correlation=None):
        headers = {"Authorization": "Bearer " + connection.token}
        headers.update(correlation or _correlation_headers({}))
        try:
            result = await client.request(
                method,
                connection.url + path,
                json=payload,
                headers=headers,
            )
        except httpx.HTTPError:
            raise HTTPException(
                502, "Server connection failed; check address and network"
            )
        if result.status_code >= 400:
            raise HTTPException(
                result.status_code,
                "Server rejected the request; check credentials, capability and configuration",
            )
        return result.json()

    @app.post("/local/connection/test")
    async def test_connection(request: Request):
        correlation = request.state.correlation
        return {
            "ready": await remote_json("GET", "/cloud/health/ready", correlation=correlation),
            "capabilities": await remote_json("GET", "/cloud/capabilities", correlation=correlation),
        }

    @app.post("/local/opencode/discover")
    def discover(payload: dict = Body(default={})):
        return importer.discover(payload.get("directory"), payload.get("file"))

    @app.post("/local/opencode/preview")
    def preview(payload: dict = Body()):
        return importer.preview(payload["source_id"])

    @app.post("/local/opencode/select-file")
    def select_config_file():
        if os.name != "nt":
            raise HTTPException(400, "The native file picker is available on Windows")
        try:
            import tkinter
            from tkinter import filedialog

            window = tkinter.Tk()
            window.withdraw()
            window.attributes("-topmost", True)
            try:
                path = filedialog.askopenfilename(
                    parent=window,
                    title="Select OpenCode configuration",
                    filetypes=[("OpenCode JSON / JSONC", "*.json *.jsonc")],
                )
            finally:
                window.destroy()
        except Exception:
            raise HTTPException(
                503, "File picker unavailable; enter the full path instead"
            )
        return importer.discover(file=path) if path else {"sources": []}

    @app.post("/local/imports/preview")
    async def preview_resources(request: Request, payload: dict = Body()):
        from admin_web.local_service.resource_import import collect

        content = await asyncio.to_thread(
            collect,
            importer,
            payload.get("file"),
            payload.get("include_external_skills", False),
        )
        try:
            response = await client.post(
                connection.url + "/cloud/admin/imports/preview",
                headers={
                    "Authorization": "Bearer " + connection.token,
                    **request.state.correlation,
                },
                files={"file": ("resources.json", content, "application/json")},
            )
        except httpx.HTTPError:
            raise HTTPException(502, "Remote resource import connection failed")
        if not response.is_success:
            raise HTTPException(
                response.status_code,
                response.json().get("detail", "Resource import failed"),
            )
        return response.json()

    @app.post("/local/opencode/import")
    async def import_config(request: Request, payload: dict = Body()):
        values = importer.take(payload["preview_id"], payload["selected"])
        return await remote_json(
            "POST",
            "/cloud/admin/models/import",
            {
                "models": values,
                "replace": payload.get("replace", False),
                "revision": payload.get("revision"),
            },
            correlation=request.state.correlation,
        )

    @app.api_route(
        "/remote/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]
    )
    async def proxy(path: str, request: Request):
        # Only relative API paths; server destination is configured separately.
        if not path or ".." in path.split("/") or path.startswith("/") or "\\" in path:
            raise HTTPException(400, "Invalid API path")
        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower()
            in {
                "content-type",
                "accept",
                "x-cloud-agent-id",
                "x-cloud-username",
                "x-cloud-session-id",
                "x-cloud-message-id",
                "last-event-id",
            }
        }
        headers.update(request.state.correlation)
        headers["Authorization"] = "Bearer " + connection.token
        target = connection.url + "/" + path
        if request.url.query:
            target += "?" + request.url.query
        is_stream = path in {"event", "global/event"} or path.endswith("/event")
        try:
            upstream_request = client.build_request(
                request.method, target, headers=headers, content=request.stream()
            )
            if is_stream:
                upstream_request.extensions["timeout"] = httpx.Timeout(
                    None, connect=10
                ).as_dict()
            response = await client.send(upstream_request, stream=True)
        except httpx.HTTPError:
            raise HTTPException(502, "Remote API connection failed")

        async def chunks():
            try:
                try:
                    async for chunk in until_stopped(
                        response.aiter_raw(), app.state.stopping
                    ):
                        yield chunk
                except httpx.HTTPError:
                    if not is_stream:
                        raise
                    # A controlled Agent replacement closes the old native event
                    # stream. End it normally so the browser reconnects and reloads
                    # history; do not turn an expected disconnect into an ASGI error.
            finally:
                await response.aclose()

        forwarded = {
            k: v
            for k, v in response.headers.items()
            if k.lower()
            in {
                "content-type",
                "content-disposition",
                "content-encoding",
                "x-accel-buffering",
                "traceparent",
                "x-cloud-trace-id",
                "x-cloud-request-id",
            }
        }
        return StreamingResponse(
            chunks(), status_code=response.status_code, headers=forwarded
        )

    dist = Path(__file__).resolve().parents[1] / "frontend/dist"

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        candidate = (dist / path).resolve()
        if candidate.is_relative_to(dist.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        index = dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(
            {
                "detail": "Frontend not built. Run npm ci and npm run build in admin_web/frontend/"
            },
            503,
        )

    return app
