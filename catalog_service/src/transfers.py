"""Bounded, transactional resource-pool imports and portable configuration exports."""

import base64
import copy
import hashlib
import io
import json
import re
import time
import uuid
import zipfile
from pathlib import PurePosixPath

from fastapi import HTTPException

from catalog_service.src.import_formats import jsonc
from catalog_service.src.management import (
    MASK,
    fail,
    identifier,
    redact,
    relative_file,
    preserve_secrets,
    validate_model,
    validate_mcp,
    unpack_skill,
)

LIMIT = 20 * 1024**2
FORMAT = "opencode-cloud-resources"
ADAPTERS = {
    "@ai-sdk/openai-compatible": "openai-compatible",
    "@ai-sdk/openai": "openai",
    "@ai-sdk/anthropic": "anthropic",
    "@ai-sdk/google": "google",
}


def item_id(value):
    return identifier(re.sub("[^a-zA-Z0-9_-]", "-", value)[:64])


def skill_item(filename, content):
    meta, files = unpack_skill(filename, content)
    return {
        "id": meta["name"],
        "kind": "skill",
        "name": meta["name"],
        "data": meta,
        "files": {
            path: base64.b64encode(value).decode() for path, value in files.items()
        },
    }


def native_zip(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        infos = archive.infolist()
        if "opencode.json" not in archive.namelist():
            return [skill_item("skill.zip", content)], []
        if len(infos) > 10000 or sum(i.file_size for i in infos) > 100 * 1024**2:
            fail("Native configuration package exceeds extraction limits", 413)
        files = {}
        for info in infos:
            path = relative_file(info.filename.rstrip("/"))
            if path in files or (info.external_attr >> 16) & 0o170000 == 0o120000:
                fail("Duplicate or symbolic-link archive entry")
            if not info.is_dir():
                files[path] = archive.read(info)
        config = jsonc(files["opencode.json"].decode("utf-8-sig"))
        items, warnings = parse_native(config)
        skill_paths = config.get("skills", {}).get("paths", [])
        for declared in skill_paths:
            prefix = relative_file(declared.removeprefix("./")).rstrip("/")
            roots = sorted(
                {
                    p.rsplit("/", 1)[0]
                    for p in files
                    if p.endswith("/SKILL.md") and (p.startswith(prefix + "/"))
                }
            )
            for root in roots:
                out = io.BytesIO()
                with zipfile.ZipFile(out, "w") as skill:
                    for path, value in files.items():
                        if path.startswith(root + "/"):
                            skill.writestr(path[len(root) + 1 :], value)
                items.append(skill_item("skill.zip", out.getvalue()))
        return items, warnings


def parse_native(config):
    if not isinstance(config, dict):
        fail("OpenCode configuration must be an object")
    items, warnings = [], []
    for name, mcp in config.get("mcp", {}).items():
        items.append({"id": item_id(name), "kind": "mcp", "name": name, "data": mcp})
    defaults = {
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com",
        "google": "https://generativelanguage.googleapis.com",
    }
    for pid, provider in config.get("provider", {}).items():
        adapter = ADAPTERS.get(provider.get("npm"), pid if pid in defaults else None)
        options = provider.get("options", {})
        for mid, model in provider.get("models", {}).items():
            target = item_id(pid + "-" + mid)
            entry = {
                "id": target,
                "kind": "model",
                "name": model.get("name", mid),
                "data": {
                    "id": target,
                    "name": model.get("name", mid),
                    "provider": adapter,
                    "upstream_model": model.get("id", mid),
                    "base_url": options.get("baseURL", defaults.get(adapter, "")),
                    "api_key": options.get("apiKey", ""),
                    "headers": options.get("headers", {}),
                    "parameters": model.get("options", {}),
                    "enabled": True,
                },
            }
            if (
                set(options) - {"apiKey", "baseURL", "headers"}
                or set(provider) - {"npm", "name", "options", "models"}
                or set(model)
                - {
                    "id",
                    "name",
                    "options",
                    "limit",
                    "temperature",
                    "top_p",
                    "max_tokens",
                }
            ):
                entry["error"] = (
                    "Unsupported provider/model fields; remove them explicitly before importing"
                )
            for name in ("context", "output"):
                if name in model.get("limit", {}):
                    entry["data"][name] = model["limit"][name]
            for name in ("temperature", "top_p", "max_tokens"):
                if name in model:
                    entry["data"]["parameters"] = {
                        **entry["data"]["parameters"],
                        name: model[name],
                    }
            if set(model.get("limit", {})) - {"context", "output"}:
                entry["error"] = "Unsupported model limit fields"
            items.append(entry)
        if not provider.get("models"):
            warnings.append("Provider " + pid + " has no explicit model declarations")
    for field in set(config) - {"$schema", "provider", "mcp", "model", "small_model"}:
        warnings.append(
            field
            + ": not imported from JSON; upload actual Skill files separately when using skills paths"
        )
    if config.get("model") or config.get("small_model"):
        warnings.append(
            "Source defaults are suggestions only: "
            + str(config.get("model"))
            + " / "
            + str(config.get("small_model"))
        )
    return items, warnings


def has_credentials(model):
    accounts = model.get("deployments")
    if accounts:
        enabled = [d for d in accounts if d.get("enabled", True)]
        return bool(enabled) and all(d.get("api_key") not in (None, "", MASK) for d in enabled)
    return model.get("api_key") not in (None, "", MASK)


class Transfers:
    def __init__(self, store, runtime=None):
        self.store = store
        self.runtime = runtime
        with store.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS resource_imports (id TEXT PRIMARY KEY, expires REAL, document TEXT, result TEXT)"
            )

    def validate(self, entry):
        identifier(entry["id"])
        for path, expected in entry.get("file_sha256", {}).items():
            if (
                path not in entry.get("files", {})
                or hashlib.sha256(
                    base64.b64decode(entry["files"][path], validate=True)
                ).hexdigest()
                != expected
            ):
                fail("Resource file checksum mismatch")
        identifier(entry["name"]) if entry["kind"] != "model" else None
        data = entry["data"]
        if entry["kind"] == "model":
            if data.get("legacy") or data.get("provider") == "legacy":
                fail(
                    "Legacy environment models must be configured explicitly before transfer"
                )
            validate_model(data)
        elif entry["kind"] == "mcp":
            entry["data"] = validate_mcp(data)
        elif entry["kind"] == "skill":
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w", zipfile.ZIP_STORED) as archive:
                for path, encoded in entry.get("files", {}).items():
                    archive.writestr(
                        relative_file(path), base64.b64decode(encoded, validate=True)
                    )
            checked = skill_item("skill.zip", stream.getvalue())
            entry.update(
                data=checked["data"], files=checked["files"], name=checked["name"]
            )
        elif entry["kind"] == "hook":
            path = relative_file(data.get("entry", "hook.mjs"))
            sources = data.get("sources", {})
            if (
                PurePosixPath(path).suffix not in {".js", ".mjs", ".ts"}
                or path not in sources
            ):
                fail("Hook entry must identify a JS/MJS/TS source")
            if (
                len(sources) > 50
                or any(not isinstance(s, str) for s in sources.values())
                or sum(len(s) for s in sources.values()) > 1024**2
            ):
                fail("Hook source limit exceeded")
            entry["files"] = {
                relative_file(p): base64.b64encode(s.encode()).decode()
                for p, s in sources.items()
            }
        else:
            fail("Unsupported resource type")
        if re.search(r"\{(?:env|file):[^}]+\}", json.dumps(data)):
            fail(
                "Unresolved local variable/file reference; resolve it locally before upload"
            )

    def preview(self, filename, content, password=None):
        if password is not None:
            if len(content) > LIMIT * 2:
                fail("Encrypted upload exceeds 40 MiB", 413)
            from catalog_service.src.encrypted_transfer import decrypt

            content = decrypt(jsonc(content.decode("utf-8-sig")), password)
            filename = "resources.json"
        if len(content) > LIMIT:
            fail("Resource upload exceeds 20 MiB", 413)
        try:
            if filename.lower().endswith(".zip"):
                items, warnings = native_zip(content)
            elif filename.lower().endswith(".md"):
                items, warnings = [skill_item(filename, content)], []
            else:
                payload = jsonc(content.decode("utf-8-sig"))
                if payload.get("format") == FORMAT:
                    if payload.get("format_version") not in {1, 2}:
                        fail("Unsupported transfer format version")
                    items, warnings = (
                        payload.get("items", []),
                        payload.get("warnings", []),
                    )
                else:
                    items, warnings = parse_native(payload)
            if not isinstance(items, list) or len(items) > 1000:
                fail("Import supports at most 1000 items")
            rev, catalog = self.store.read()
            normalized = []
            for index, original in enumerate(items):
                entry = copy.deepcopy(original)
                entry["key"] = str(index)
                try:
                    self.validate(entry)
                    existing = catalog[
                        "models" if entry["kind"] == "model" else "resources"
                    ].get(entry["id"])
                    entry["conflict"] = bool(existing)
                    if entry["kind"] == "model" and not has_credentials(entry["data"]):
                        entry.setdefault("warnings", []).append(
                            "API key missing: new model will remain disabled until configured"
                        )
                    if entry["kind"] == "mcp" and entry["data"]["type"] == "local":
                        entry.setdefault("warnings", []).append(
                            "Command runs in the server sandbox; review paths and installed dependencies"
                        )
                except HTTPException as exc:
                    entry["error"] = str(exc.detail)
                normalized.append(entry)
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
            fail("Invalid resource configuration")
        preview_id = "imp_" + uuid.uuid4().hex
        templates = (
            payload.get("agent_templates", [])
            if "payload" in locals() and payload.get("format") == FORMAT
            else []
        )
        if not isinstance(templates, list) or len(templates) > 1000:
            fail("Invalid Agent template list")
        from catalog_service.src.admin_dto import AgentDefinition

        try:
            for template in templates:
                identifier(template["id"])
                AgentDefinition.model_validate(template["config"])
        except (ValueError, TypeError, KeyError, AttributeError):
            fail("Invalid Agent template configuration")
        document = {
            "revision": rev,
            "items": normalized,
            "warnings": warnings,
            "agent_templates": templates,
            "source_sha256": hashlib.sha256(content).hexdigest(),
        }
        with self.store.connect() as db:
            db.execute("DELETE FROM resource_imports WHERE expires < ?", (time.time(),))
            db.execute(
                "INSERT INTO resource_imports VALUES (?,?,?,NULL)",
                (preview_id, time.time() + 900, json.dumps(document)),
            )
        public = redact(document)
        for entry in public["items"]:
            entry["files"] = sorted(entry.get("files", {}))
        return {"preview_id": preview_id, **public}

    def commit(self, preview_id, selections):
        # One SQLite transaction commits resources and the idempotency result.
        with self.store.lock, self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT expires,document,result FROM resource_imports WHERE id=?",
                (preview_id,),
            ).fetchone()
            if not row or row[0] < time.time():
                fail("Import preview expired; select the source again", 409)
            if row[2]:
                previous = json.loads(row[2])
                if previous["selections"] != selections:
                    fail(
                        "This preview was already committed with different selections",
                        409,
                    )
                return previous["result"]
            document = json.loads(row[1])
            revision, raw = db.execute(
                "SELECT revision,document FROM catalog WHERE id=1"
            ).fetchone()
            if revision != document["revision"]:
                fail("Resource catalog changed; preview again before importing", 409)
            catalog = json.loads(raw)
            if not selections:
                fail("Select at least one resource")
            seen, result = set(), []
            by_key = {e["key"]: e for e in document["items"]}
            for selection in selections:
                entry = copy.deepcopy(by_key.get(selection["key"]))
                if not entry or entry.get("error"):
                    fail("Cannot import an invalid resource")
                target = identifier(selection["target_id"])
                pool = catalog["models" if entry["kind"] == "model" else "resources"]
                identity = ("model" if entry["kind"] == "model" else "resource", target)
                if identity in seen:
                    fail("Duplicate destination ID")
                seen.add(identity)
                old = pool.get(target)
                if old and not selection.get("replace"):
                    fail(
                        "Destination exists; rename or explicitly replace its draft",
                        409,
                    )
                if (
                    old
                    and entry["kind"] != "model"
                    and (old["kind"] != entry["kind"] or old.get("owner"))
                ):
                    fail(
                        "Cannot replace a different resource type or an Agent private resource",
                        409,
                    )
                if entry["kind"] == "model":
                    model = preserve_secrets(entry["data"], old or {})
                    model["id"] = target
                    model["api_key"] = model.get("api_key") or ""
                    for account in model.get("deployments", []):
                        account["api_key"] = account.get("api_key") or ""
                    if not has_credentials(model):
                        model["enabled"] = False
                    validate_model(model)
                    if (
                        old
                        and not model.get("enabled", True)
                        and self.store.model_references(catalog, target)
                    ):
                        fail(
                            "Replace Agent model references before disabling this model",
                            409,
                        )
                    pool[target] = model
                else:
                    data = preserve_secrets(
                        entry["data"], old["draft"]["data"] if old else {}
                    )
                    if entry["kind"] == "mcp":
                        for field in ("headers", "environment"):
                            if field in data:
                                if any(value is None for value in data[field].values()):
                                    data["enabled"] = False
                                data[field] = {
                                    key: value or ""
                                    for key, value in data[field].items()
                                }
                        validate_mcp(data)
                    files = {
                        p: self.store.blob(base64.b64decode(v))
                        for p, v in entry.get("files", {}).items()
                    }
                    resource = old or {
                        "id": target,
                        "kind": entry["kind"],
                        "owner": None,
                        "archived": False,
                        "versions": [],
                    }
                    resource.update(
                        name=entry["name"], draft={"data": data, "files": files}
                    )
                    pool[target] = resource
                result.append({"kind": entry["kind"], "id": target})
            from catalog_service.src.agent_templates import remap_template

            mapping = {
                (
                    "model" if by_key[s["key"]]["kind"] == "model" else "resource",
                    by_key[s["key"]]["id"],
                ): s["target_id"]
                for s in selections
            }
            templates = []
            for template in document.get("agent_templates", []):
                value = remap_template(template, mapping)
                tid = "tpl_" + uuid.uuid4().hex
                value.update(id=tid, source_id=template["id"], imported=True)
                catalog.setdefault("agent_templates", {})[tid] = value
                templates.append(tid)
            response = {
                "imported": result,
                "assigned_agents": [],
                "published": False,
                "agent_templates": templates,
            }
            db.execute(
                "UPDATE catalog SET revision=?,document=? WHERE id=1",
                (revision + 1, json.dumps(catalog)),
            )
            db.execute(
                "UPDATE resource_imports SET result=? WHERE id=?",
                (
                    json.dumps({"selections": selections, "result": response}),
                    preview_id,
                ),
            )
            return response

    def export(self, include_secrets=False):
        _, catalog = self.store.read()
        items, warnings = [], []
        environment = {}
        if self.runtime:
            try:
                environment = self.runtime.gateway_environment()
            except Exception:
                warnings.append(
                    "Gateway environment unavailable; legacy model references must be mapped during restore"
                )
        for mid, model in catalog["models"].items():
            if model.get("legacy"):
                prefix = mid.upper().replace("-", "_")
                if prefix + "_MODEL" not in environment:
                    warnings.append(
                        mid
                        + ": legacy environment model excluded; configure a managed model before migration"
                    )
                    continue
                protocol, upstream = environment[prefix + "_MODEL"].split("/", 1)
                adapter = {
                    "openai": "openai-compatible",
                    "anthropic": "anthropic",
                    "gemini": "google",
                }.get(protocol)
                if not adapter:
                    fail("Unsupported legacy model protocol for export: " + protocol)
                model = {
                    "id": mid,
                    "name": model.get("name", mid),
                    "provider": adapter,
                    "upstream_model": upstream,
                    "base_url": environment[prefix + "_1_API_BASE"],
                    "additional_base_urls": [environment[prefix + "_2_API_BASE"]],
                    "api_key": environment[prefix + "_API_KEY"],
                    "parameters": {},
                    "enabled": model.get("enabled", True),
                }
            items.append(
                {
                    "id": mid,
                    "kind": "model",
                    "name": model.get("name", mid),
                    "data": copy.deepcopy(model) if include_secrets else redact(model),
                }
            )
        total = 0
        for rid, resource in catalog["resources"].items():
            files = {}
            for path, digest in resource["draft"].get("files", {}).items():
                raw = self.store.file(digest)
                total += len(raw)
                if total > LIMIT // 2:
                    fail(
                        "Resource export exceeds the current size limit; export smaller Skills separately",
                        413,
                    )
                files[path] = base64.b64encode(raw).decode()
            items.append(
                {
                    "id": rid,
                    "kind": resource["kind"],
                    "name": resource["name"],
                    "data": copy.deepcopy(resource["draft"]["data"])
                    if include_secrets
                    else redact(resource["draft"]["data"]),
                    "files": files,
                    "source_owner": resource.get("owner"),
                }
            )
        templates = []
        version_ids = {}
        for rid, resource in catalog["resources"].items():
            for version in resource["versions"]:
                vid = (
                    "version-"
                    + hashlib.sha256(
                        (rid + ":" + str(version["version"])).encode()
                    ).hexdigest()[:32]
                )
                version_ids[(rid, version["version"])] = vid
                files = {
                    p: base64.b64encode(self.store.file(d)).decode()
                    for p, d in version.get("files", {}).items()
                }
                items.append(
                    {
                        "id": vid,
                        "kind": resource["kind"],
                        "name": resource["name"],
                        "data": copy.deepcopy(version["data"])
                        if include_secrets
                        else redact(version["data"]),
                        "files": files,
                        "source_owner": resource.get("owner"),
                        "source_resource": rid,
                        "source_version": version["version"],
                    }
                )
        for aid, agent in catalog["agents"].items():
            variants = [("draft", agent["draft"])] + [
                (str(v["version"]), v["config"]) for v in agent["versions"]
            ]
            for label, config in variants:
                cfg = copy.deepcopy(config)
                for binding in cfg["bindings"]:
                    binding["id"] = version_ids[(binding["id"], binding["version"])]
                    binding["version"] = 1
                templates.append(
                    {
                        "id": item_id(aid + "-" + label),
                        "name": config["name"] + " / " + label,
                        "config": cfg,
                        "source_agent": aid,
                        "source_version": label,
                    }
                )
        for item in items:
            item["file_sha256"] = {
                p: hashlib.sha256(base64.b64decode(v)).hexdigest()
                for p, v in item.get("files", {}).items()
            }
        content = json.dumps(
            {
                "format": FORMAT,
                "format_version": 2,
                "minimum_server_version": "0.3.0",
                "items": items,
                "agent_templates": templates,
                "warnings": warnings,
            },
            ensure_ascii=False,
        ).encode()
        if len(content) > LIMIT:
            fail("Resource export exceeds 20 MiB", 413)
        return content
