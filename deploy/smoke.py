#!/usr/bin/env python3
"""Standard-library smoke client for an installed OpenCode Cloud deployment."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import os
from pathlib import Path
from typing import Any


TIMEOUT = 600


class SmokeError(RuntimeError):
    def __init__(self, code: str, status: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class Client:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        token_path = Path(__file__).resolve().parents[1] / 'data/admin-token'
        self.token = os.environ.get('CLOUD_AGENT_ADMIN_TOKEN') or (token_path.read_text().strip() if token_path.is_file() else '')

    def request(
        self, method: str, path: str, *, body: bytes | None = None,
        headers: dict[str, str] | None = None, expected: tuple[int, ...] = (200,),
    ) -> tuple[int, dict[str, str], bytes]:
        request = urllib.request.Request(self.base_url + path, data=body, method=method)
        if self.token:
            request.add_header('Authorization', 'Bearer ' + self.token)
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            with self.opener.open(request, timeout=TIMEOUT) as response:
                status = response.status
                response_headers = {name.lower(): value for name, value in response.headers.items()}
                content = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            response_headers = {name.lower(): value for name, value in exc.headers.items()}
            content = b""
            exc.close()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SmokeError(type(exc).__name__) from exc
        if status not in expected:
            raise SmokeError("UnexpectedHTTPStatus", status)
        return status, response_headers, content

    def json(
        self, method: str, path: str, payload: Any | None = None, *,
        headers: dict[str, str] | None = None, expected: tuple[int, ...] = (200,),
    ) -> tuple[int, dict[str, str], Any]:
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        status, response_headers, content = self.request(
            method, path, body=body, headers=request_headers, expected=expected
        )
        try:
            decoded = json.loads(content) if content else None
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise SmokeError("InvalidJSONResponse", status) from exc
        return status, response_headers, decoded

    def sse_probe(self, path: str, headers: dict[str, str]) -> dict[str, Any]:
        request = urllib.request.Request(self.base_url + path, method="GET")
        if self.token:
            request.add_header('Authorization', 'Bearer ' + self.token)
        for name, value in headers.items():
            request.add_header(name, value)
        try:
            with self.opener.open(request, timeout=TIMEOUT) as response:
                content_type = response.headers.get_content_type()
                if response.status != 200 or content_type != "text/event-stream":
                    raise SmokeError("InvalidSSEResponse", response.status)
                first_chunk = response.read1(128)
                if not first_chunk:
                    raise SmokeError("EmptySSEStream", response.status)
                return {"status": response.status, "content_type": content_type, "first_chunk_bytes": len(first_chunk)}
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            raise SmokeError("UnexpectedHTTPStatus", status) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SmokeError(type(exc).__name__) from exc


def multipart(fields: dict[str, str], filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = "----cloud-smoke-" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"), b"\r\n",
        ])
    chunks.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: application/octet-stream\r\n\r\n", content, b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def create_session(client: Client, agent: str, username: str) -> str:
    _, _, payload = client.json(
        "POST", "/session", {"_cloud": {"agent_id": agent, "username": username}}
    )
    session_id = payload.get("id") if isinstance(payload, dict) else None
    if not isinstance(session_id, str) or not session_id:
        raise SmokeError("InvalidSessionResponse")
    return session_id


def ordinary_smoke(client: Client, fixture: str, sessions: list[str]) -> dict[str, Any]:
    _, _, ready = client.json("GET", "/cloud/health/ready")
    if not isinstance(ready, dict) or ready.get("ok") is not True:
        raise SmokeError("ReadinessFailed")
    _, _, document = client.json("GET", "/doc")
    if not isinstance(document, dict) or "/api/session" not in document.get("paths", {}) or "x-cloud-routing" not in document:
        raise SmokeError("PublicApiDocumentFailed")
    users = {
        "agent-code": f"smoke-code-{fixture}",
        "agent-data": f"smoke-data-{fixture}",
    }
    created: dict[str, list[str]] = {}
    native_health: dict[str, Any] = {}
    for agent, username in users.items():
        pair = []
        for _ in range(2):
            session_id = create_session(client, agent, username)
            sessions.append(session_id)
            pair.append(session_id)
        created[agent] = pair
        for session_id in pair:
            _, _, payload = client.json("GET", f"/session/{urllib.parse.quote(session_id)}")
            if not isinstance(payload, dict) or payload.get("id") != session_id:
                raise SmokeError("NativeSessionLookupFailed")
        other = f"conflict-{fixture}"
        client.request(
            "GET", f"/session/{urllib.parse.quote(pair[0])}",
            headers={"X-Cloud-Agent-ID": agent, "X-Cloud-Username": other}, expected=(409,),
        )
        _, _, health = client.json(
            "GET", "/global/health",
            headers={"X-Cloud-Agent-ID": agent, "X-Cloud-Username": username},
        )
        if not isinstance(health, dict) or health.get("healthy") is not True:
            raise SmokeError("NativeHealthFailed")
        native_health[agent] = {"healthy": True, "version": health.get("version")}

    owner_agent = "agent-code"
    owner_user = users[owner_agent]
    file_content = ("cloud-smoke-file-" + fixture).encode("ascii")
    relative_path = f"smoke-{fixture}/marker.bin"
    body, content_type = multipart(
        {"agent_id": owner_agent, "username": owner_user, "relative_path": relative_path},
        "marker.bin", file_content,
    )
    upload_status, _, upload_body = client.request(
        "POST", "/cloud/files/upload", body=body, headers={"Content-Type": content_type}
    )
    try:
        uploaded = json.loads(upload_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SmokeError("InvalidJSONResponse", upload_status) from exc
    expected_hash = hashlib.sha256(file_content).hexdigest()
    if uploaded.get("sha256") != expected_hash or uploaded.get("size") != len(file_content):
        raise SmokeError("UploadVerificationFailed")
    query = urllib.parse.urlencode({"agent_id": owner_agent, "username": owner_user, "path": f"smoke-{fixture}"})
    _, _, listed = client.json("GET", "/cloud/files/list?" + query)
    if not any(item.get("name") == "marker.bin" for item in listed.get("entries", [])):
        raise SmokeError("FileListVerificationFailed")
    query = urllib.parse.urlencode({"agent_id": owner_agent, "username": owner_user, "path": relative_path})
    _, _, downloaded = client.request("GET", "/cloud/files/download?" + query)
    if downloaded != file_content:
        raise SmokeError("DownloadVerificationFailed")

    return {
        "ready": True, "users": users, "sessions_per_agent": 2,
        "cross_user_conflicts": 2, "native_health": native_health,
        "files": {"path": relative_path, "size": len(file_content), "sha256": expected_hash},
        "sse": {
            "event": client.sse_probe(
                "/event", {"X-Cloud-Agent-ID": owner_agent, "X-Cloud-Username": owner_user}
            ),
            "global_event": client.sse_probe(
                "/global/event", {"X-Cloud-Agent-ID": owner_agent, "X-Cloud-Username": owner_user}
            ),
        },
    }


def burst_one(client: Client, agent: str, username: str, model: str, marker: str) -> tuple[str, str]:
    session_id = create_session(client, agent, username)
    try:
        _, _, payload = client.json(
            "POST", f"/session/{urllib.parse.quote(session_id)}/message",
            {
                "model": {"providerID": "cloud-model-gateway", "modelID": model},
                "parts": [{"type": "text", "text": f"Repeat this marker exactly: {marker}"}],
            },
        )
        if not isinstance(payload, dict) or (payload.get("info") or {}).get("error"):
            raise SmokeError("ModelResponseError")
        info = payload.get("info") or {}
        text = "".join(
            part.get("text", "") for part in payload.get("parts", []) if part.get("type") == "text"
        )
        if info.get("modelID") != model or marker not in text:
            raise SmokeError("ModelResponseMismatch")
        return session_id, marker
    except BaseException:
        try:
            client.request("DELETE", f"/session/{urllib.parse.quote(session_id)}", expected=(200, 204))
        finally:
            raise


def burst_smoke(client: Client, fixture: str, sessions: list[str]) -> dict[str, Any]:
    work = []
    users: set[str] = set()
    for agent, model in (("agent-code", "coding-fast"), ("agent-data", "data-fast")):
        for user_index in range(2):
            username = f"burst-{agent.removeprefix('agent-')}-{user_index}-{fixture}"
            users.add(username)
            for request_index in range(2):
                marker = f"stage35-{fixture}-{agent}-{user_index}-{request_index}"
                work.append((agent, username, model, marker))
    started = time.perf_counter()
    successes = []
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        future_map = {
            pool.submit(burst_one, client, agent, username, model, marker): marker
            for agent, username, model, marker in work
        }
        for future in concurrent.futures.as_completed(future_map):
            marker = future_map[future]
            try:
                session_id, returned_marker = future.result()
                sessions.append(session_id)
                successes.append(returned_marker)
            except Exception as exc:
                failures.append({
                    "marker": marker, "error_code": getattr(exc, "code", type(exc).__name__),
                    "status": getattr(exc, "status", None),
                })
    elapsed = time.perf_counter() - started
    return {
        "requests": 8, "successes": len(successes), "failures": failures,
        "elapsed_seconds": round(elapsed, 3), "users": sorted(users),
        "per_http_timeout_seconds": TIMEOUT,
    }


def run(base_url: str, output: Path, burst: bool) -> dict[str, Any]:
    fixture = uuid.uuid4().hex[:10]
    client = Client(base_url)
    sessions: list[str] = []
    fixture_users = [f"smoke-code-{fixture}", f"smoke-data-{fixture}"]
    if burst:
        fixture_users.extend(
            f"burst-{agent}-{index}-{fixture}"
            for agent in ("code", "data") for index in range(2)
        )
    parsed_target = urllib.parse.urlsplit(base_url)
    if parsed_target.port is not None:
        target = f"{parsed_target.scheme}://{parsed_target.hostname}:{parsed_target.port}"
    else:
        target = f"{parsed_target.scheme}://{parsed_target.hostname or ''}"
    report: dict[str, Any] = {
        "result": "running", "fixture": fixture, "target": target,
        "fixture_users": sorted(fixture_users),
    }
    cleanup_failures: list[dict[str, Any]] = []
    try:
        report["ordinary"] = ordinary_smoke(client, fixture, sessions)
        if burst:
            report["burst"] = burst_smoke(client, fixture, sessions)
            if report["burst"]["failures"] or report["burst"]["successes"] != 8:
                raise SmokeError("BurstFailed")
        report["result"] = "passed"
    except Exception as exc:
        report.update(
            result="failed", error_code=getattr(exc, "code", type(exc).__name__),
            status=getattr(exc, "status", None),
        )
    finally:
        for session_id in sessions:
            try:
                client.request("DELETE", f"/session/{urllib.parse.quote(session_id)}", expected=(200, 204))
            except Exception as exc:
                cleanup_failures.append({
                    "session_id": session_id,
                    "error_code": getattr(exc, "code", type(exc).__name__),
                    "status": getattr(exc, "status", None),
                })
        report["created_sessions"] = sessions
        report["session_cleanup_failures"] = cleanup_failures
        if cleanup_failures:
            report["result"] = "failed"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--burst", action="store_true")
    args = parser.parse_args()
    report = run(args.base_url, args.output, args.burst)
    print(json.dumps({"result": report["result"], "output": str(args.output)}))
    raise SystemExit(report["result"] != "passed")


if __name__ == "__main__":
    main()
