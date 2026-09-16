"""Versioned management catalog. SQLite transactions never modify live sandboxes."""

from __future__ import annotations

import base64
import configparser
import copy
import hashlib
import io
import json
import re
import sqlite3
import stat
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from fastapi import HTTPException

MASK = "••••"
SECRET_FIELDS = {"api_key", "apiKey", "headers", "extra_headers", "environment"}
MODEL_PARAMETERS = {
    "temperature",
    "top_p",
    "max_tokens",
    "max_completion_tokens",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    "reasoning_effort",
}


def fail(message, status=400):
    raise HTTPException(status, message)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", value
    ):
        fail("ID must contain 1–64 letters, digits, underscores or hyphens")
    return value


def redact(value):
    if isinstance(value, dict):
        return {
            k: ({n: MASK for n in v} if isinstance(v, dict) else MASK)
            if k in SECRET_FIELDS and v
            else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def preserve_secrets(new, old):
    if new == MASK:
        return copy.deepcopy(old)
    if isinstance(new, dict):
        previous = old if isinstance(old, dict) else {}
        if new.get('deployments') and not previous.get('deployments') and previous.get('api_key'):
            previous = {**previous, 'deployments': [
                {'id': 'primary', 'api_key': previous['api_key']},
                *[{'id': f'extra-{i}', 'api_key': previous['api_key']}
                  for i, _ in enumerate(previous.get('additional_base_urls', []), 1)],
            ]}
        return {
            k: preserve_secrets(v, previous.get(k))
            for k, v in new.items()
        }
    if isinstance(new, list):
        # Deployment credentials follow stable identity, never their row position.
        previous = {item['id']: item for item in (old or []) if isinstance(item, dict) and 'id' in item}
        return [preserve_secrets(item, previous.get(item.get('id'), {}))
                if isinstance(item, dict) and 'id' in item else copy.deepcopy(item) for item in new]
    return new


def relative_file(value):
    if not isinstance(value, str) or "\\" in value or ":" in value or "\x00" in value:
        fail("Invalid resource file path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or any(p in {"..", "."} for p in value.split("/"))
        or not path.parts
    ):
        fail("Resource file escapes root")
    return path.as_posix()


def skill_metadata(content):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeError:
        fail("SKILL.md must be UTF-8")
    match = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|$)", text, re.S)
    if not match:
        fail("SKILL.md requires name and description frontmatter")
    fields = {}
    for line in match[1].splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            fields[k] = v.strip().strip("\"'")
    name = fields.get("name", "")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
        fail("Skill name must be lowercase words separated by hyphens")
    if not fields.get("description") or fields["description"] in {"|", ">"}:
        fail("Skill description must be a non-empty single-line value")
    return {"name": name, "description": fields["description"]}


def unpack_skill(filename, content):
    if len(content) > 20 * 1024**2:
        fail("Skill upload exceeds 20 MiB", 413)
    if filename.lower().endswith(".md"):
        files = {"SKILL.md": content}
    elif filename.lower().endswith(".zip"):
        files, folded, size = {}, set(), 0
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if len(archive.infolist()) > 1100:
                    fail("Too many ZIP entries")
                for entry in archive.infolist():
                    path = relative_file(entry.orig_filename.rstrip("/"))
                    kind = stat.S_IFMT(entry.external_attr >> 16)
                    if (
                        kind not in {0, stat.S_IFREG, stat.S_IFDIR}
                        or entry.flag_bits & 1
                    ):
                        fail(
                            "Links, special files and encrypted ZIP entries are unsupported"
                        )
                    if path.casefold() in folded:
                        fail("Duplicate ZIP target")
                    folded.add(path.casefold())
                    if entry.is_dir():
                        continue
                    size += entry.file_size
                    if size > 100 * 1024**2 or len(files) >= 1000:
                        fail("Skill archive exceeds unpacked limits", 413)
                    with archive.open(entry) as stream:
                        data = stream.read(min(entry.file_size + 1, 100 * 1024**2 + 1))
                    if len(data) != entry.file_size:
                        fail("ZIP size mismatch")
                    files[path] = data
        except (zipfile.BadZipFile, RuntimeError, OSError):
            fail("Invalid ZIP archive")
        roots = [p for p in files if PurePosixPath(p).name == "SKILL.md"]
        if len(roots) != 1:
            fail("ZIP must contain exactly one SKILL.md")
        prefix = roots[0][: -len("SKILL.md")]
        if any(not p.startswith(prefix) for p in files):
            fail("All files must belong to the Skill root")
        files = {p[len(prefix) :]: v for p, v in files.items()}
    else:
        fail("Upload SKILL.md or a ZIP containing one Skill")
    meta = skill_metadata(files["SKILL.md"])
    return meta, files


def validate_mcp(data):
    allowed = {
        "type",
        "url",
        "headers",
        "timeout",
        "enabled",
        "command",
        "cwd",
        "environment",
        "oauth",
    }
    if set(data) - allowed:
        fail("Unsupported MCP configuration field")
    if data.get("oauth", False) is not False:
        fail("MCP OAuth is not supported")
    if (
        not isinstance(data.get("timeout", 10000), int)
        or not 1 <= data.get("timeout", 10000) <= 120000
    ):
        fail("MCP timeout must be 1–120000 ms")
    for field in ("headers", "environment"):
        if field in data and (
            not isinstance(data[field], dict)
            or any(
                not isinstance(k, str)
                or not isinstance(v, str)
                or "\n" in k
                or "\r" in k
                for k, v in data[field].items()
            )
        ):
            fail("MCP headers/environment must contain string values")
    if data.get("type") == "remote":
        url = urlparse(data.get("url", ""))
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
        ):
            fail("MCP URL must be HTTP(S), without embedded credentials")
        if "command" in data or "environment" in data or "cwd" in data:
            fail("Remote MCP cannot contain command settings")
        data["oauth"] = False
    elif data.get("type") == "local":
        command = data.get("command")
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(x, str) or not x for x in command)
        ):
            fail("MCP command must be a non-empty string array")
        if "url" in data or "headers" in data:
            fail("Local MCP cannot contain remote settings")
        executable = PurePosixPath(command[0]).name
        if executable in {
            "npx",
            "npm",
            "pnpm",
            "yarn",
            "uvx",
            "pip",
            "pip3",
            "bash",
            "sh",
            "cmd",
            "powershell",
        }:
            fail(
                "Use an already installed MCP executable; installers and shell wrappers are unsupported"
            )
        if data.get("cwd") and (
            not PurePosixPath(data["cwd"]).is_relative_to("/workspace")
            or ".." in PurePosixPath(data["cwd"]).parts
        ):
            fail("MCP cwd must be under /workspace")
    else:
        fail("MCP type must be local or remote")
    return data


def validate_model(model):
    identifier(model.get("id"))
    allowed = {
        "id",
        "name",
        "provider",
        "upstream_model",
        "base_url",
        "additional_base_urls",
        "api_key",
        "deployments",
        "headers",
        "parameters",
        "context",
        "output",
        "enabled",
        "legacy",
    }
    if set(model) - allowed:
        fail("Unsupported model fields: " + ", ".join(sorted(set(model) - allowed)))
    if model.get("provider") not in {
        "openai",
        "openai-compatible",
        "anthropic",
        "google",
        "legacy",
    }:
        fail("Unsupported provider")
    if not isinstance(model.get("upstream_model"), str) or not model["upstream_model"]:
        fail("Upstream model is required")
    if model.get("base_url"):
        url = urlparse(model["base_url"])
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
        ):
            fail("Model URL must be HTTP(S), without embedded credentials")
    alternatives = model.get("additional_base_urls", [])
    if not isinstance(alternatives, list) or len(alternatives) > 7:
        fail("At most seven equivalent additional endpoints are supported")
    for base in alternatives:
        if not isinstance(base, str):
            fail("Additional endpoints must be URLs")
        url = urlparse(base)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
        ):
            fail("Additional model URL must be HTTP(S), without embedded credentials")
    parameters = model.get("parameters", {})
    if not isinstance(parameters, dict) or set(parameters) - MODEL_PARAMETERS:
        fail("Unsupported model parameters")
    if any(
        not isinstance(v, (int, float, str)) or isinstance(v, bool)
        for v in parameters.values()
    ):
        fail("Invalid model parameter value")
    if not isinstance(model.get("headers", {}), dict) or any(
        not isinstance(v, str) for v in model.get("headers", {}).values()
    ):
        fail("Headers must be string values")
    for key in ("context", "output"):
        if model.get(key) is not None and (
            not isinstance(model[key], int) or model[key] < 1
        ):
            fail("Model token limits must be positive integers")
    if model.get('provider') != 'legacy':
        from shared_libs.model_routing import deployment_entries
        try:
            deployment_entries(model)
        except ValueError as error:
            fail(str(error))
    elif model.get('deployments'):
        fail('Convert the legacy model before adding deployments')
    return model


class ManagementStore:
    def __init__(self, root: Path, agents_root: Path):
        self.root, self.agents_root = Path(root), Path(agents_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self.blobs = self.root / "blobs"
        self.blobs.mkdir(exist_ok=True)
        self.path = self.root / "catalog.db"
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS catalog (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, document TEXT NOT NULL)"
            )
            db.execute(
                "INSERT OR IGNORE INTO catalog VALUES (1,0,?)",
                (
                    json.dumps(
                        {
                            "models": {},
                            "resources": {},
                            "agents": {},
                            "jobs": {},
                            "gateway_versions": [],
                            "gateway_active": None,
                        }
                    ),
                ),
            )
        self.path.chmod(0o600)
        self.migrate()
        self.bootstrap()

    def migrate(self):
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                fail("Management database was created by a newer server", 409)
            if version == 1:
                return
            backup_root = self.root / "migrations"
            backup_root.mkdir(exist_ok=True, mode=0o700)
            backup = backup_root / ("catalog-v0-" + uuid.uuid4().hex + ".sqlite")
            with sqlite3.connect(backup) as destination:
                db.backup(destination)
            backup.chmod(0o600)
            db.execute("BEGIN IMMEDIATE")
            revision, document = db.execute(
                "SELECT revision,document FROM catalog WHERE id=1"
            ).fetchone()
            data = json.loads(document)
            data.setdefault("agent_tombstones", {})
            data.setdefault("sandbox_operations", {})
            data.setdefault("bootstrapped", bool(data["agents"]))
            for agent in data["agents"].values():
                agent.setdefault("lifecycle", "active")
            db.execute(
                "UPDATE catalog SET revision=?,document=? WHERE id=1",
                (revision + 1, json.dumps(data)),
            )
            db.execute("PRAGMA user_version = 1")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def read(self):
        with self.lock, self.connect() as db:
            revision, document = db.execute(
                "SELECT revision, document FROM catalog WHERE id=1"
            ).fetchone()
            data = json.loads(document)
            data[
                "jobs"
            ] = {}  # Compatibility view; execution state belongs to operations.
            return revision, data

    @contextmanager
    def edit(self, expected=None):
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            revision, document = db.execute(
                "SELECT revision, document FROM catalog WHERE id=1"
            ).fetchone()
            if expected is not None and expected != revision:
                fail("Configuration changed; reload before saving", 409)
            data = json.loads(document)
            data["jobs"] = {}
            yield data
            data.pop("jobs", None)
            data.pop("sandbox_operations", None)
            db.execute(
                "UPDATE catalog SET revision=?, document=? WHERE id=1",
                (revision + 1, json.dumps(data, ensure_ascii=False)),
            )

    def blob(self, content):
        digest = hashlib.sha256(content).hexdigest()
        path = self.blobs / digest
        if not path.exists():
            path.write_bytes(content)
        return digest

    def file(self, digest):
        if not re.fullmatch("[a-f0-9]{64}", digest):
            fail("Invalid blob ID")
        return (self.blobs / digest).read_bytes()

    def bootstrap(self):
        if self.read()[1].get("bootstrapped"):
            return
        with self.edit() as data:
            if data.get("bootstrapped"):
                return
            data["bootstrapped"] = True
            # Bundled examples are templates, never active business records.
            for kind, model in (("code", "glm"), ("data", "minimax")):
                folder = self.agents_root / ("agent-" + kind)
                instructions = folder / "AGENTS.md"
                data.setdefault("agent_templates", {}).setdefault("example-" + kind, {
                    "id": "example-" + kind,
                    "name": "Code 示例" if kind == "code" else "Data 示例",
                    "config": {
                        "name": "Code" if kind == "code" else "Data",
                        "description": "可编辑的内置示例，恢复后需要发布。",
                        "enabled": True,
                        "instructions": instructions.read_text(encoding="utf-8") if instructions.exists() else "",
                        "allowed_model_ids": [model], "default_model_id": model,
                        "small_model_id": None, "bindings": [],
                    },
                })

    @staticmethod
    def resource_version(data, rid, version):
        resource = data["resources"].get(rid)
        if not resource:
            fail("Resource not found", 404)
        result = next(
            (v for v in resource["versions"] if v["version"] == version), None
        )
        if result is None:
            fail("Published resource version not found", 404)
        return resource, result

    @staticmethod
    def agent_config(agent):
        version = next(
            (v for v in agent["versions"] if v["version"] == agent["active"]), None
        )
        return version["config"] if version else None

    def validate_agent(self, data, aid, cfg):
        for field, choices in (
            ("cpu_limit", (1, 2, 4, 8)),
            ("memory_mb", (1024, 2048, 4096, 8192)),
        ):
            value = cfg.get(field)
            if value is not None and (type(value) is not int or value not in choices):
                fail(f"{field} must be one of {choices}, or null for server default")
        allowed = cfg.get("allowed_model_ids", [])
        if (
            not isinstance(allowed, list)
            or not allowed
            or len(allowed) != len(set(allowed))
        ):
            fail("Choose one or more unique models")
        for mid in allowed:
            if mid not in data["models"] or (
                cfg.get("enabled", True)
                and not data["models"][mid].get("enabled", True)
            ):
                fail("Agent references an unavailable model: " + str(mid))
        if cfg.get("default_model_id") not in allowed or (
            cfg.get("small_model_id") and cfg["small_model_id"] not in allowed
        ):
            fail("Default and small models must be assigned to this Agent")
        names, ids = set(), set()
        if not isinstance(cfg.get("bindings", []), list):
            fail("Bindings must be a list")
        for binding in cfg.get("bindings", []):
            resource, version = self.resource_version(
                data, binding["id"], binding["version"]
            )
            if resource["owner"] not in {None, aid}:
                fail("Cannot bind another Agent’s private resource", 403)
            key = (resource["kind"], version["data"].get("name", resource["name"]))
            if key in names or resource["id"] in ids:
                fail("Duplicate resource binding or runtime name")
            names.add(key)
            ids.add(resource["id"])
        if (
            not isinstance(cfg.get("instructions", ""), str)
            or len(cfg.get("instructions", "")) > 200000
        ):
            fail("Agent instructions are too large")

    def save_model(self, mid, value, expected=None):
        with self.edit(expected) as data:
            value = preserve_secrets(value, data["models"].get(mid, {}))
            value["id"] = identifier(mid)
            validate_model(value)
            if value.get("provider") == "legacy" and not data["models"].get(
                mid, {}
            ).get("legacy"):
                fail("Legacy models can only be migrated from the existing deployment")
            if not value.get("enabled", True):
                refs = self.model_references(data, mid, enabled_only=True)
                if refs:
                    fail("Model is referenced by: " + ", ".join(refs), 409)
            data["models"][mid] = value

    def model_references(self, data, mid, *, enabled_only=False):
        return [
            aid
            for aid, agent in data["agents"].items()
            if any(
                mid in config.get("allowed_model_ids", [])
                and (not enabled_only or config.get("enabled", True))
                for config in (agent["draft"], self.agent_config(agent) or {})
            )
        ]

    def save_agent(self, aid, value, expected=None, source=None):
        identifier(aid)
        with self.edit(expected) as data:
            if aid in data.get("agent_tombstones", {}):
                fail("This Agent ID was retired; choose a new ID", 409)
            if data["agents"].get(aid, {}).get("lifecycle") == "deleting" or (
                source and data["agents"].get(source, {}).get("lifecycle") == "deleting"
            ):
                fail("Agent deletion is in progress", 409)
            if any(
                j["status"] in {"queued", "validating", "waiting", "applying"}
                and j["target"] in {aid, "*"}
                for j in data["jobs"].values()
            ):
                fail("An operation affects this Agent; wait before editing", 409)
            if source:
                if aid in data["agents"] or source not in data["agents"]:
                    fail("Invalid copy source or destination", 409)
                value = copy.deepcopy(data["agents"][source]["draft"])
                value["name"] = aid
                for binding in value["bindings"]:
                    r = data["resources"][binding["id"]]
                    if r["owner"] == source:
                        new_id = "r-" + uuid.uuid4().hex[:20]
                        copied = copy.deepcopy(r)
                        copied.update(id=new_id, owner=aid)
                        data["resources"][new_id] = copied
                        binding["id"] = new_id
            old = data["agents"].get(aid)
            self.validate_agent(data, aid, value)
            if old:
                old["draft"] = value
            else:
                data["agents"][aid] = {
                    "id": aid,
                    "draft": value,
                    "versions": [],
                    "active": None,
                }

    def save_resource(self, rid, value, expected=None):
        identifier(rid)
        with self.edit(expected) as data:
            old = data["resources"].get(rid)
            if value.get("kind") not in {"skill", "mcp", "hook"}:
                fail("Invalid resource kind")
            owner = value.get("owner") or None
            if owner and owner not in data["agents"]:
                fail("Owner Agent does not exist")
            if owner and data["agents"][owner].get("lifecycle") == "deleting":
                fail("Agent deletion is in progress", 409)
            if old and (old["kind"] != value["kind"] or old["owner"] != owner):
                fail("Resource kind and ownership are immutable")
            name = identifier(value["name"])
            content = preserve_secrets(
                value.get("data", {}), old["draft"]["data"] if old else {}
            )
            files = old["draft"].get("files", {}) if old else {}
            if value["kind"] == "mcp":
                content = validate_mcp(content)
            elif value["kind"] == "hook":
                entry = relative_file(content.get("entry", "hook.mjs"))
                sources = content.get("sources", {entry: content.get("source", "")})
                if (
                    PurePosixPath(entry).suffix not in {".js", ".mjs", ".ts"}
                    or entry not in sources
                ):
                    fail("Hook entry must be a JS/MJS/TS source file")
                if len(sources) > 50 or sum(len(s) for s in sources.values()) > 1024**2:
                    fail("Hook source limit exceeded")
                files = {
                    relative_file(p): self.blob(s.encode("utf-8"))
                    for p, s in sources.items()
                }
                content = {"entry": entry, "sources": sources}
            elif not old:
                fail("Create Skill resources using the upload endpoint")
            if old:
                old.update(
                    name=name,
                    archived=bool(value.get("archived", False)),
                    draft={"data": content, "files": files},
                )
            else:
                data["resources"][rid] = {
                    "id": rid,
                    "name": name,
                    "kind": value["kind"],
                    "owner": owner,
                    "archived": False,
                    "draft": {"data": content, "files": files},
                    "versions": [],
                }

    def resource_lifecycle(self, rid, action, expected=None):
        with self.edit(expected) as data:
            resource = data["resources"].get(rid)
            if not resource:
                fail("Resource not found", 404)
            if action in {"archive", "restore"}:
                resource["archived"] = action == "archive"
                return
            if action != "delete":
                fail("Unknown resource action")
            if not resource.get("archived"):
                fail("请先归档资源，再永久删除", 409)
            references = []
            for aid, agent in data["agents"].items():
                configs = [agent["draft"]] + [v["config"] for v in agent["versions"]]
                if any(b["id"] == rid for cfg in configs for b in cfg.get("bindings", [])):
                    references.append("Agent " + aid)
            for tid, template in data.get("agent_templates", {}).items():
                if any(b["id"] == rid for b in template["config"].get("bindings", [])):
                    references.append("模板 " + tid)
            if references:
                fail("资源仍被草稿、已发布版本或历史版本引用，不能删除：" + ", ".join(references), 409)
            # Blobs can be shared by immutable resources/exports; delete only the
            # catalog entry, never remove shared content while dropping metadata.
            del data["resources"][rid]

    def upload_skill(self, rid, filename, content, owner=None, expected=None):
        identifier(rid)
        meta, files = unpack_skill(filename, content)
        blobs = {p: self.blob(v) for p, v in files.items()}
        with self.edit(expected) as data:
            old = data["resources"].get(rid)
            if owner and owner not in data["agents"]:
                fail("Unknown owner")
            if owner and data["agents"][owner].get("lifecycle") == "deleting":
                fail("Agent deletion is in progress", 409)
            if old and (old["kind"] != "skill" or old["owner"] != owner):
                fail("Resource kind and owner cannot change")
            resource = old or {
                "id": rid,
                "kind": "skill",
                "owner": owner,
                "versions": [],
                "archived": False,
            }
            resource.update(name=meta["name"], draft={"data": meta, "files": blobs})
            data["resources"][rid] = resource

    def publish_resource(self, rid, checked_draft):
        with self.edit() as data:
            resource = data["resources"].get(rid)
            if not resource or resource["draft"] != checked_draft:
                fail("Draft changed during validation; retry", 409)
            version = len(resource["versions"]) + 1
            resource["versions"].append(
                {
                    "version": version,
                    "created": time.time(),
                    **copy.deepcopy(checked_draft),
                }
            )
            return version

    def public_catalog(self, compact=False):
        revision, data = self.read()
        result = {
            "revision": revision,
            **redact({k: v for k, v in data.items() if k != "releases"}),
        }
        for mid, model in result["models"].items():
            model["references"] = self.model_references(data, mid)
        if compact:
            result["jobs"] = dict(
                sorted(
                    result["jobs"].items(),
                    key=lambda item: item[1]["created"],
                    reverse=True,
                )[:25]
            )
            for agent in result["agents"].values():
                agent["versions"] = [
                    {k: v[k] for k in ("version", "created") if k in v}
                    for v in agent["versions"]
                ]
            for resource in result["resources"].values():
                resource["versions"] = [
                    {k: v[k] for k in ("version", "created") if k in v}
                    for v in resource["versions"]
                ]
            result["gateway_versions"] = [
                {k: v[k] for k in ("version", "created") if k in v}
                for v in result["gateway_versions"]
            ]
        return result
