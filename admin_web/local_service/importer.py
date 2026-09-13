"""Bounded local config discovery and secret-preserving OpenCode model import."""

import json
import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from admin_web.local_service.formats import fail, redact, validate_model


def jsonc(text):
    out, i, quoted, escape = [], 0, False, False
    while i < len(text):
        char = text[i]
        if quoted:
            out.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                quoted = False
            i += 1
        elif char == '"':
            quoted = True
            out.append(char)
            i += 1
        elif text[i : i + 2] == "//":
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
        elif text[i : i + 2] == "/*":
            end = text.find("*/", i + 2)
            if end < 0:
                fail("Unterminated JSONC comment")
            out.append(" ")
            i = end + 2
        else:
            out.append(char)
            i += 1
    # Remove trailing commas outside JSON strings.
    text, out, quoted, escape = "".join(out), [], False, False
    for i, char in enumerate(text):
        if not quoted and char == "," and text[i + 1 :].lstrip().startswith(("}", "]")):
            continue
        out.append(char)
        if quoted:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
    try:
        value = json.loads("".join(out).lstrip("\ufeff"))
        if not isinstance(value, dict):
            fail("OpenCode config must be an object")
        return value
    except ValueError:
        fail("Invalid JSON/JSONC configuration")


class Importer:
    def __init__(self, home=None):
        self.home = Path(home or Path.home()).resolve()
        self.sources, self.previews = {}, {}

    def discover(self, directory=None, file=None):
        config_home = Path(
            os.environ.get("XDG_CONFIG_HOME", str(self.home / ".config"))
        )
        paths = [
            config_home / "opencode" / n for n in ("opencode.json", "opencode.jsonc")
        ]
        for env in ("OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR"):
            value = os.environ.get(env)
            if value:
                p = Path(value).expanduser()
                paths.extend(
                    [p]
                    if env == "OPENCODE_CONFIG"
                    else [p / n for n in ("opencode.json", "opencode.jsonc")]
                )
        if directory:
            p = Path(directory).expanduser().resolve()
            paths.extend(
                p / n
                for n in (
                    "opencode.json",
                    "opencode.jsonc",
                    ".opencode/opencode.json",
                    ".opencode/opencode.jsonc",
                )
            )
        if file:
            p = Path(file).expanduser().resolve()
            if p.suffix.lower() not in {".json", ".jsonc"}:
                fail("Select a JSON or JSONC configuration")
            paths.append(p)
        result = []
        for p in dict.fromkeys(paths):
            if str(p).startswith("\\\\") or not p.is_file():
                continue
            resolved = p.resolve()
            key = (
                next((k for k, v in self.sources.items() if v == resolved), None)
                or uuid.uuid4().hex
            )
            self.sources[key] = resolved
            result.append({"id": key, "path": str(resolved), "bytes": p.stat().st_size})
        return {"sources": result}

    def resolve_value(self, value, parent):
        if isinstance(value, dict):
            return {k: self.resolve_value(v, parent) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve_value(v, parent) for v in value]
        if not isinstance(value, str):
            return value

        def replace(match):
            kind, name = match.group(1), match.group(2)
            if kind == "env":
                if name not in os.environ:
                    fail("Missing environment variable: " + name)
                return os.environ[name]
            p = Path(name).expanduser()
            if not p.is_absolute():
                p = parent / p
            p = p.resolve()
            if not (p.is_relative_to(self.home) or p.is_relative_to(parent)) or str(
                p
            ).startswith("\\\\"):
                fail(
                    "Referenced file is outside the chosen configuration directory and user home"
                )
            if not p.is_file() or p.stat().st_size > 65536:
                fail("Referenced credential file is missing or too large")
            return p.read_text(encoding="utf-8").strip()

        return re.sub(r"\{(env|file):([^}]+)\}", replace, value)

    def preview(self, source_id):
        source = self.sources.get(source_id)
        if not source or not source.is_file() or source.stat().st_size > 2 * 1024**2:
            fail("Configuration is unavailable or exceeds 2 MiB")
        raw = jsonc(source.read_text(encoding="utf-8-sig"))
        # Only resolve model fields. Do not read unrelated MCP/plugin file references.
        raw = {
            k: v for k, v in raw.items() if k in {"provider", "model", "small_model"}
        }
        config = self.resolve_value(raw, source.parent)
        auth = {}
        data_home = Path(
            os.environ.get("XDG_DATA_HOME", str(self.home / ".local/share"))
        )
        auth_path = data_home / "opencode/auth.json"
        if auth_path.is_file() and auth_path.stat().st_size < 2 * 1024**2:
            auth = jsonc(auth_path.read_text(encoding="utf-8-sig"))
        items, errors, source_models = [], [], {}
        adapters = {
            "@ai-sdk/openai-compatible": "openai-compatible",
            "@ai-sdk/openai": "openai",
            "@ai-sdk/anthropic": "anthropic",
            "@ai-sdk/google": "google",
        }
        defaults = {
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com",
            "google": "https://generativelanguage.googleapis.com",
        }
        for pid, provider in config.get("provider", {}).items():
            try:
                adapter = adapters.get(
                    provider.get("npm"), pid if pid in defaults else None
                )
                if adapter is None:
                    fail("Unsupported provider adapter")
                options = provider.get("options", {})
                unsupported = set(options) - {"apiKey", "baseURL", "headers"}
                if unsupported:
                    fail(
                        "Unsupported provider options: "
                        + ", ".join(sorted(unsupported))
                    )
                credential = auth.get(pid, {})
                key = options.get("apiKey") or (
                    credential.get("key") if credential.get("type") == "api" else None
                )
                if not key:
                    fail("API key unavailable (OAuth sessions cannot be imported)")
                base = options.get("baseURL", defaults.get(adapter, ""))
                url = urlparse(base)
                if url.hostname in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
                    fail(
                        "Local model URL is not reachable by the server; change baseURL before importing"
                    )
                for mid, model in provider.get("models", {}).items():
                    supported = {
                        "id",
                        "name",
                        "limit",
                        "options",
                        "temperature",
                        "top_p",
                        "max_tokens",
                    }
                    if set(model) - supported:
                        fail(
                            "Unsupported model fields: "
                            + ", ".join(sorted(set(model) - supported))
                        )
                    if set(model.get("limit", {})) - {"context", "output"}:
                        fail(
                            "Unsupported model limit fields; retain context and output only"
                        )
                    model_id = re.sub("[^a-zA-Z0-9_-]", "-", pid + "-" + mid)[:64]
                    entry = {
                        "id": model_id,
                        "name": model.get("name", mid),
                        "provider": adapter,
                        "upstream_model": model.get("id", mid),
                        "base_url": base,
                        "api_key": key,
                        "headers": options.get("headers", {}),
                        "parameters": dict(model.get("options", {})),
                        "enabled": True,
                    }
                    for key_name in ("temperature", "top_p", "max_tokens"):
                        if key_name in model:
                            entry["parameters"][key_name] = model[key_name]
                    for name in ("context", "output"):
                        if name in model.get("limit", {}):
                            entry[name] = model["limit"][name]
                    validate_model(entry)
                    items.append(entry)
                    source_models[pid + "/" + mid] = model_id
            except Exception as exc:
                from fastapi import HTTPException

                errors.append(
                    {
                        "provider": pid,
                        "error": exc.detail
                        if isinstance(exc, HTTPException)
                        else "Invalid provider structure",
                    }
                )
        if len({m["id"] for m in items}) != len(items):
            errors.append(
                {
                    "error": "Imported model IDs collide; rename provider or model entries"
                }
            )
        if not items:
            errors.append({"error": "No explicit supported model definitions found"})
        self.previews = {
            k: v for k, v in self.previews.items() if v["expires"] > time.time()
        }
        preview_id = uuid.uuid4().hex
        self.previews[preview_id] = {
            "models": items,
            "errors": errors,
            "expires": time.time() + 900,
        }
        return {
            "preview_id": preview_id,
            "models": redact(items),
            "errors": errors,
            "model": config.get("model"),
            "small_model": config.get("small_model"),
            "suggested_default_model_id": source_models.get(config.get("model")),
            "suggested_small_model_id": source_models.get(config.get("small_model")),
            "note": "Models only; no MCP, Skills, plugins or permissions will be imported.",
        }

    def take(self, preview_id, selected):
        preview = self.previews.get(preview_id)
        if not preview or preview["expires"] < time.time():
            fail("Import preview expired; scan again", 409)
        if preview["errors"]:
            fail("Resolve import errors before continuing")
        values = [m for m in preview["models"] if m["id"] in selected]
        if not values or len(values) != len(set(selected)):
            fail("Select valid models from this preview")
        return values
