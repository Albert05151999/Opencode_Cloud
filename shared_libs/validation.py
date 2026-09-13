"""Configuration validation shared by separately packaged consumers."""

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
        return {
            k: preserve_secrets(v, old.get(k) if isinstance(old, dict) else None)
            for k, v in new.items()
        }
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
    return model
