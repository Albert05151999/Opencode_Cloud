"""Catalog API adapter; immutable Agent bundles cached by version."""

import base64
import binascii
import errno
import json
import os
import tempfile
import threading
from pathlib import Path

import httpx
from fastapi import HTTPException

from sandbox_manager.agents import AgentCatalog
from shared_libs.service import internal_sync_client
from shared_libs.validation import relative_file
from shared_libs.workspace_paths import validate_identifier


def install_bundle(root, agent_id, bundle):
    validate_identifier(agent_id, "agent_id")
    files = bundle.get("files", {})
    if not isinstance(files, dict) or len(files) > 2000:
        raise HTTPException(413, "Agent bundle exceeds file limit")
    version = validate_identifier(str(bundle.get("version", "preview")), "version")
    target = Path(root) / "versions" / version / agent_id
    if target.is_dir():
        # The response is still fetched on every load: no stale version/admission cache.
        # Compare immutable bytes directly without rewriting a staging tree on every request.
        proposed = {}
        size = 0
        for name, value in files.items():
            name = relative_file(name)
            if not isinstance(value, str):
                raise HTTPException(422, "Agent bundle files must be base64 strings")
            if len(value) > ((100 * 1024**2 - size + 2) // 3) * 4:
                raise HTTPException(413, "Agent bundle exceeds size limit")
            try:
                raw = base64.b64decode(value, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise HTTPException(422, "Invalid Agent bundle encoding") from exc
            size += len(raw)
            if size > 100 * 1024**2:
                raise HTTPException(413, "Agent bundle exceeds size limit")
            proposed[name] = raw
        if "agent.cfg" not in proposed:
            raise HTTPException(422, "Agent bundle missing agent.cfg")
        current = {str(x.relative_to(target)): x.read_bytes() for x in target.rglob("*") if x.is_file()}
        if current != proposed:
            raise HTTPException(409, "Immutable bundle version already exists with different content")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".bundle-", dir=target.parent))
    size = 0
    try:
        for name, value in files.items():
            name = relative_file(name)
            if not isinstance(value, str):
                raise HTTPException(422, "Agent bundle files must be base64 strings")
            if len(value) > ((100 * 1024**2 - size + 2) // 3) * 4:
                raise HTTPException(413, "Agent bundle exceeds size limit")
            try:
                raw = base64.b64decode(value, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise HTTPException(422, "Invalid Agent bundle encoding") from exc
            size += len(raw)
            if size > 100 * 1024**2:
                raise HTTPException(413, "Agent bundle exceeds size limit")
            dest = staging / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            dest.chmod(0o644)
        if not (staging / "agent.cfg").is_file():
            raise HTTPException(422, "Agent bundle missing agent.cfg")
        for directory in [staging, *[x for x in staging.rglob("*") if x.is_dir()]]:
            directory.chmod(0o755)
        if target.exists():
            # Immutable versions must never silently change contents.
            current = {
                str(x.relative_to(target)): x.read_bytes()
                for x in target.rglob("*")
                if x.is_file()
            }
            proposed = {
                str(x.relative_to(staging)): x.read_bytes()
                for x in staging.rglob("*")
                if x.is_file()
            }
            if current != proposed:
                raise HTTPException(
                    409,
                    "Immutable bundle version already exists with different content",
                )
        else:
            try:
                os.replace(staging, target)
            except OSError as exc:
                if (
                    exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}
                    or not target.is_dir()
                ):
                    raise
                # Another process may have installed this immutable version.
                current = {
                    str(x.relative_to(target)): x.read_bytes()
                    for x in target.rglob("*")
                    if x.is_file()
                }
                proposed = {
                    str(x.relative_to(staging)): x.read_bytes()
                    for x in staging.rglob("*")
                    if x.is_file()
                }
                if current != proposed:
                    raise HTTPException(
                        409,
                        "Immutable bundle version already exists with different content",
                    ) from exc
        return target
    finally:
        import shutil

        if staging.exists():
            shutil.rmtree(staging)


class RemoteCatalog:
    def __init__(self, config, root, gateway_url):
        self.root, self.gateway_url = Path(root), gateway_url
        self.root.mkdir(parents=True, exist_ok=True)
        self.override_path = self.root / "applied.json"
        self._lock = threading.RLock()
        self.overrides = (
            json.loads(self.override_path.read_text())
            if self.override_path.exists()
            else {}
        )
        self.client = internal_sync_client(config, "catalog_service")

    def _persist(self, overrides):
        fd, temporary = tempfile.mkstemp(prefix=".applied-", dir=self.root)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(overrides, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.override_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _definition(self, agent_id, path):
        path = Path(path).resolve()
        if not path.is_relative_to(self.root.resolve()) or path.name != agent_id:
            raise HTTPException(422, "Applied Agent bundle is outside its cache")
        definition = AgentCatalog(path.parent, gateway_url=self.gateway_url).load(
            agent_id
        )
        if (
            definition.opencode["provider"]["cloud-model-gateway"]["options"].get(
                "apiKey"
            )
            != "{env:MODEL_GATEWAY_TOKEN}"
        ):
            raise HTTPException(
                422, "Agent model credential must reference MODEL_GATEWAY_TOKEN"
            )
        return definition

    def _authoritative(self, agent_id):
        response = self.client.get(f"/internal/v1/agents/{agent_id}/bundle")
        if response.is_error:
            raise HTTPException(response.status_code, "Catalog bundle unavailable")
        return install_bundle(self.root, agent_id, response.json())

    def stage(self, agent_id, path):
        validate_identifier(agent_id, "agent_id")
        definition = self._definition(agent_id, path)
        with self._lock:
            updated = {**self.overrides, agent_id: str(definition.path)}
            self._persist(updated)
            self.overrides = updated
        return definition

    def commit(self, agent_id):
        validate_identifier(agent_id, "agent_id")
        with self._lock:
            staged = self.overrides.get(agent_id)
            if staged is None:
                return self.load(agent_id)
            authoritative = self._authoritative(agent_id)
            if authoritative.resolve() != Path(staged).resolve():
                raise HTTPException(
                    409, "Catalog has not committed the staged Agent version"
                )
            definition = self._definition(agent_id, authoritative)
            updated = {
                key: value for key, value in self.overrides.items() if key != agent_id
            }
            self._persist(updated)
            self.overrides = updated
            return definition

    def load(self, agent_id):
        validate_identifier(agent_id, "agent_id")
        with self._lock:
            path = self.overrides.get(agent_id)
            if path is None:
                path = self._authoritative(agent_id)
            return self._definition(agent_id, path)


class Admission:
    def __init__(self, config):
        self.catalog = internal_sync_client(config, "catalog_service")
        self.requests, self.acquiring, self.blocked = {}, {}, set()
        self.control = internal_sync_client(config, "operations")
        self.operations = self
        self.load_tests = self

    def resources_for(self, agent_id, username):
        response = self.control.get(
            "/internal/v1/admission",
            params={"agent_id": agent_id, "username": username},
        )
        if response.is_error:
            raise HTTPException(
                response.status_code,
                response.json().get("detail", "Runtime admission denied"),
            )
        item = response.json().get("resources")
        if not item:
            return None
        return {
            "cpu_limit": item.get("cpu", item.get("cpu_limit")),
            "memory_mb": item["memory_mb"],
            "run_id": item.get("load_test", item.get("run_id")),
        }

    def check_acquire_local(self, agent_id, username):
        if agent_id in self.blocked or "*" in self.blocked:
            raise HTTPException(503, "Agent lifecycle operation in progress")

    def check_acquire(self, agent_id, username):
        self.check_acquire_local(agent_id, username)
        self.resources_for(agent_id, username)

    def active_user(self, agent_id, username):
        # LoadTestStore creates reserved loadtest- usernames exclusively.
        # This is classification for monitoring, never an acquire authorization.
        if not username.startswith("loadtest-"):
            return False
        return bool(self.resources_for(agent_id, username))

    def authorize(self, aid, method, path, payload):
        if (aid in self.blocked or "*" in self.blocked) and not path.endswith(
            ("/abort", "/interrupt")
        ):
            raise HTTPException(503, "Agent lifecycle operation in progress")
        response = self.catalog.post(
            f"/internal/v1/agents/{aid}/authorize",
            json={"method": method, "path": path, "payload": payload},
        )
        if response.is_error:
            raise HTTPException(
                response.status_code,
                response.json().get("detail", "Agent authorization failed"),
            )
        result = response.json()
        if isinstance(payload, dict) and isinstance(result.get("payload"), dict):
            payload.clear()
            payload.update(result["payload"])
        return result["mutation"]

    def lease(self, aid, begin):
        self.requests[aid] = max(0, self.requests.get(aid, 0) + (1 if begin else -1))
