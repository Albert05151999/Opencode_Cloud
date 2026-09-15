"""Catalog resource API and immutable, versioned compilation contracts."""

import base64
import hashlib
import shutil
import copy
import json
import os
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, HTTPException
from shared_libs.service import configure_service, settings, internal_client
from .src.management import ManagementStore, fail, identifier, redact
from .src.compiler import Compiler
from .src.admin_api import create_admin_router
from .src.transfers_api import create_transfers_router


def bundle(path):
    return {
        p.relative_to(path).as_posix(): base64.b64encode(p.read_bytes()).decode()
        for p in path.rglob("*")
        if p.is_file() and not p.is_symlink()
    }


class Runtime(Compiler):
    def __init__(self, store, config, service_config):
        super().__init__(store, config)
        self.service_config = service_config
        self.client = internal_client(service_config, "sandbox_manager")

    def gateway_environment(self):
        return dict(os.environ)

    async def test_model(self, model_id):
        async with internal_client(self.service_config, "model_gateway") as client:
            try:
                response = await client.post(
                    "/cloud/admin/models/" + model_id + "/test", json={}, timeout=90
                )
                if response.is_error:
                    fail(
                        response.json().get("detail", "Model test failed"),
                        response.status_code,
                    )
                return response.json()
            except httpx.HTTPError:
                fail("Model gateway unavailable", 503)

    async def remote(self, path, payload):
        try:
            r = await self.client.post(path, json=payload, timeout=180)
            if r.is_error:
                fail(r.json().get("detail", "Runtime validation failed"), r.status_code)
            return r.json()
        except httpx.HTTPError:
            fail("Sandbox manager unavailable", 503)

    async def probe(self, path, *, mcp=False):
        return await self.remote(
            "/internal/v1/probes", {"files": bundle(path), "mcp": mcp}
        )

    async def compile_hook(self, draft):
        files = {
            p: base64.b64encode(self.store.file(d)).decode()
            for p, d in draft["files"].items()
        }
        result = await self.remote("/internal/v1/hooks/compile", {"files": files})
        checked = copy.deepcopy(draft)
        checked["files"] = {
            p: self.store.blob(base64.b64decode(v)) for p, v in result["files"].items()
        }
        return checked


def create_app(data_root=None):
    service_config = settings("catalog_service")
    root = Path(data_root or service_config["data_root"])
    options = service_config["settings"]
    store = ManagementStore(
        root,
        Path(
            os.environ.get(
                "CATALOG_SEED_ROOT",
                (
                    options.get("seed_root")
                    or str(Path(__file__).parent / "resources/agents")
                ),
            )
        ),
    )
    config = SimpleNamespace(
        model_gateway=SimpleNamespace(
            base_url=os.environ.get(
                "MODEL_GATEWAY_PUBLIC_URL",
                options.get(
                    "model_gateway_public_url", "http://host.docker.internal:8104/v1"
                ),
            )
        ),
        sandbox=SimpleNamespace(
            image=os.environ.get(
                "AGENT_RUNTIME_IMAGE",
                options.get(
                    "agent_runtime_image", "opencode-cloud/agent_runtime:1.0.0"
                ),
            ),
            **{
                **dict(
                    idle_timeout_seconds=1800,
                    default_cpu=2,
                    default_memory_mb=2048,
                    default_pids=256,
                ),
                **options.get("sandbox", {}),
            },
        ),
    )
    runtime = Runtime(store, config, service_config)
    # Seed configuration is imported once into catalog-owned immutable artifacts.
    # Deployment templates never remain the writable/active source of truth.
    revision, seeded = store.read()
    replacements = []
    for aid, agent in seeded["agents"].items():
        for version in agent["versions"]:
            old = Path(version["path"])
            packaged_seed = (
                old.resolve().parent == store.agents_root.resolve()
                and old.name == aid
                and (old / "agent.cfg").is_file()
            )
            if packaged_seed:
                compiled = runtime.compile_agent(
                    seeded, aid, version["config"], version["version"]
                )
                replacements.append((aid, version["version"], str(compiled)))
            elif not old.is_dir() or not all(
                (old / name).is_file() for name in ("agent.cfg", "opencode.json")
            ):
                raise RuntimeError(
                    f"Catalog artifact missing for {aid} version {version['version']}; restore the immutable artifact from backup"
                )
    if replacements:
        with store.edit(revision) as imported:
            for aid, number, path in replacements:
                next(
                    v
                    for v in imported["agents"][aid]["versions"]
                    if v["version"] == number
                )["path"] = path

    @asynccontextmanager
    async def lifespan(app):
        yield
        await runtime.client.aclose()

    app = FastAPI(title="catalog_service", version="1.0.0", lifespan=lifespan)
    configure_service(app, "catalog_service", service_config)
    app.state.store = store
    app.include_router(create_admin_router(store, runtime))
    app.include_router(create_transfers_router(store, runtime))

    @app.get("/health/ready")
    def ready():
        store.read()
        return {"ready": True, "module": "catalog_service"}

    @app.get("/internal/v1/load-test-catalog")
    def load_catalog():
        _, data = store.read()
        return {"agents": data["agents"]}

    @app.get("/internal/v1/agents/{aid}/bundle")
    def active_bundle(aid: str):
        _, data = store.read()
        a = data["agents"].get(aid)
        if not a or a["active"] is None:
            fail("Agent has no active configuration", 404)
        v = next(v for v in a["versions"] if v["version"] == a["active"])
        return {
            "agent_id": aid,
            "version": v["version"],
            "config": v["config"],
            "files": bundle(Path(v["path"])),
        }

    @app.post("/internal/v1/agents/{aid}/authorize")
    def authorize(aid: str, payload: dict):
        body = payload.get("payload")
        mutation = runtime.authorize(aid, payload["method"], payload["path"], body)
        return {"mutation": mutation, "payload": body}

    @app.post("/internal/v1/releases/prepare")
    def prepare(payload: dict):
        revision, data = store.read()
        if payload.get("revision") is not None and payload["revision"] != revision:
            fail("Configuration changed; reload", 409)
        kind, target = payload["kind"], payload.get("target", "*")
        rid = uuid.uuid4().hex
        if kind == "models.apply":
            models = data["models"]
            if payload.get("version"):
                old = next(
                    (
                        v
                        for v in data["gateway_versions"]
                        if v["version"] == payload["version"]
                    ),
                    None,
                )
                if old is None:
                    fail("Unknown gateway version", 404)
                models = old["models"]
            for aid, a in data["agents"].items():
                active_config = store.agent_config(a) or {}
                if active_config.get("enabled", True) and set(
                    active_config.get("allowed_model_ids", [])
                ) - set(k for k, v in models.items() if v.get("enabled", True)):
                    fail("Model is used by " + aid, 409)
            value = {
                "kind": kind,
                "target": "*",
                "version": len(data["gateway_versions"]) + 1,
                "models": models,
                "configuration": runtime.gateway_configuration(
                    models, dict(os.environ), require_credentials=True
                ),
            }
        else:
            identifier(target)
            a = data["agents"].get(target)
            if not a:
                fail("Agent not found", 404)
            if a.get("lifecycle") == "deleting":
                fail("Finish permanent deletion before applying configuration", 409)
            cfg = a["draft"]
            if payload.get("version"):
                old = next(
                    (v for v in a["versions"] if v["version"] == payload["version"]),
                    None,
                )
                if old is None:
                    fail("Agent version not found", 404)
                cfg = old["config"]
            active_models = next(
                (
                    v["models"]
                    for v in data["gateway_versions"]
                    if v["version"] == data["gateway_active"]
                ),
                None,
            )
            available = active_models or {
                mid: m for mid, m in data["models"].items() if m.get("legacy")
            }
            if set(cfg["allowed_model_ids"]) - {
                mid for mid, m in available.items() if m.get("enabled", True)
            }:
                fail("Publish selected models to the gateway first", 409)
            number = len(a["versions"]) + 1
            path = runtime.compile_agent(data, target, cfg, number)
            value = {
                "kind": kind,
                "target": target,
                "version": number,
                "config": cfg,
                "path": str(path),
                "files": bundle(path),
            }
        value.update(
            release_id=rid,
            revision=revision,
            old_active=data["gateway_active"]
            if target == "*"
            else data["agents"][target]["active"],
        )
        with store.edit(revision) as latest:
            latest.setdefault("releases", {})[rid] = value
        return value

    @app.get("/internal/v1/releases/{rid}")
    def release_status(rid: str):
        _, data = store.read()
        value = data.get("releases", {}).get(rid)
        if not value:
            fail("Release not found", 404)
        return value

    @app.post("/internal/v1/releases/{rid}/commit")
    def commit(rid: str):
        with store.edit() as data:
            value = data.get("releases", {}).get(rid)
            if not value:
                fail("Release not found", 404)
            if value.get("committed"):
                return {"version": value["version"]}
            if value["kind"] == "models.apply":
                if data["gateway_active"] != value["old_active"]:
                    fail("Applied version changed", 409)
                data["gateway_versions"].append(
                    {
                        "version": value["version"],
                        "created": time.time(),
                        "models": value["models"],
                    }
                )
                data["gateway_active"] = value["version"]
            else:
                a = data["agents"][value["target"]]
                if a["active"] != value["old_active"]:
                    fail("Applied version changed", 409)
                a["versions"].append(
                    {k: value[k] for k in ("version", "config", "path")}
                    | {"created": time.time()}
                )
                a["active"] = value["version"]
            value["committed"] = True
        return {"version": value["version"]}

    @app.post("/internal/v1/agents/{aid}/operation-check")
    def operation_check(aid: str, payload: dict):
        revision, data = store.read()
        a = data["agents"].get(aid)
        if not a:
            fail("Agent not found", 404)
        if payload.get("revision") is not None and payload["revision"] != revision:
            fail("Configuration changed; reload before operating", 409)
        kind = payload["kind"]
        lifecycle = a.get("lifecycle", "active")
        if lifecycle == "deleting" and kind != "agent.delete":
            fail("Finish permanent deletion before using this Agent ID", 409)
        if kind in {
            "sandbox.start",
            "sandbox.restart",
            "sandbox.recover",
        } and lifecycle in {"archived", "deleting"}:
            fail("Restore archived Agent first", 409)
        if kind == "agent.restore" and lifecycle not in {"archived", "deleting"}:
            fail("Agent is not archived", 409)
        if kind == "agent.archive" and lifecycle in {"archived", "deleting"}:
            fail("Agent is already archived", 409)
        if kind == "agent.delete-empty" and (
            a["versions"]
            or any(r.get("owner") == aid for r in data["resources"].values())
        ):
            fail(
                "Only an unpublished Agent without private resources can be deleted here",
                409,
            )
        return {"ok": True, "revision": revision, "lifecycle": lifecycle}

    @app.get("/internal/v1/agents/{aid}/deletion-impact")
    def impact(aid: str):
        revision, data = store.read()
        if aid not in data["agents"]:
            fail("Agent not found", 404)
        a = data["agents"][aid]
        private = {k: v for k, v in data["resources"].items() if v.get("owner") == aid}
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "agent": {k: v for k, v in a.items() if k != "lifecycle"},
                    "private_resources": private,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return {
            "agent_id": aid,
            "revision": revision,
            "lifecycle": a.get("lifecycle", "active"),
            "private_resources": sorted(private),
            "fingerprint": fingerprint,
        }

    @app.post("/internal/v1/agents/{aid}/lifecycle")
    def lifecycle(aid: str, payload: dict):
        with store.edit(payload.get("revision")) as data:
            a = data["agents"].get(aid)
            if not a:
                tombstone = data.get("agent_tombstones", {}).get(aid, {})
                if payload.get("action") == "delete" and tombstone.get(
                    "request_id"
                ) == payload.get("request_id"):
                    return {"ok": True}
                fail("Agent not found", 404)
            action = payload["action"]
            if payload.get("expected_fingerprint"):
                private = {
                    k: v for k, v in data["resources"].items() if v.get("owner") == aid
                }
                actual = hashlib.sha256(
                    json.dumps(
                        {
                            "agent": {k: v for k, v in a.items() if k != "lifecycle"},
                            "private_resources": private,
                        },
                        sort_keys=True,
                    ).encode()
                ).hexdigest()
                if actual != payload["expected_fingerprint"]:
                    fail("Catalog deletion impact changed", 409)
            if action == "delete":
                if a.get("lifecycle") not in {"archived", "deleting"}:
                    fail("Archive the Agent before permanent deletion", 409)
                compiled = (store.root / "compiled").resolve()
                for version in a["versions"]:
                    path = Path(version["path"])
                    if path.is_relative_to(compiled):
                        if (
                            path.is_symlink()
                            or not path.resolve().is_relative_to(compiled)
                            or path.name != aid
                        ):
                            fail("Compiled configuration path changed", 409)
                        if path.exists():
                            shutil.rmtree(path)
                data["resources"] = {
                    k: v for k, v in data["resources"].items() if v.get("owner") != aid
                }
                del data["agents"][aid]
                data.setdefault("agent_tombstones", {})[aid] = {
                    "deleted": time.time(),
                    "request_id": payload.get("request_id"),
                }
            elif action in {"archive", "restore", "deleting"}:
                a["lifecycle"] = {
                    "archive": "archived",
                    "restore": "active",
                    "deleting": "deleting",
                }[action]
            else:
                fail("Unknown lifecycle action")
        return {"ok": True}

    @app.post("/cloud/admin/models/test-draft")
    async def test_draft(payload: dict):
        from .src.management import preserve_secrets, validate_model

        _, data = store.read()
        model = payload.get("model", {})
        model = preserve_secrets(model, data["models"].get(model.get("id"), {}))
        validate_model(model)
        async with internal_client(service_config, "model_gateway") as client:
            try:
                response = await client.post(
                    "/cloud/admin/models/test-draft", json={"model": model}, timeout=90
                )
                if response.is_error:
                    fail(
                        response.json().get("detail", "Model test failed"),
                        response.status_code,
                    )
                return response.json()
            except httpx.HTTPError:
                fail("Model gateway unavailable", 503)

    @app.get("/cloud/admin/provider-templates")
    def provider_templates():
        return json.loads(
            (Path(__file__).parent / "src/provider_templates.json").read_text(encoding='utf-8')
        )

    @app.post("/cloud/admin/models/config-preview")
    def model_preview(payload: dict):
        from .src.management import validate_model

        model = payload["model"]
        validate_model(model)
        configuration = runtime.gateway_configuration({model['id']: model}, {})
        return redact(
            {
                "gateway": configuration['model_list'],
                "router_settings": configuration['router_settings'],
                "agent": {
                    'model': 'cloud-model-gateway/' + model['id'],
                    'provider': {'cloud-model-gateway': {
                        'npm': '@ai-sdk/openai-compatible',
                        'options': {'baseURL': config.model_gateway.base_url, 'apiKey': '{env:MODEL_GATEWAY_TOKEN}'},
                        'models': {model['id']: {'name': model.get('name') or model['id']}},
                    }},
                },
            }
        )

    return app


app = create_app()

if __name__ == "__main__":
    from shared_libs.service import run

    run("catalog_service")
