"""Validated, atomic model configuration activation owned by this service."""

import copy
import json
import logging
import os
from pathlib import Path
from fastapi import HTTPException


def validate_release(payload):
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("release_id"), str)
        or not payload["release_id"]
    ):
        raise HTTPException(422, "release_id is required")
    config = payload.get("configuration")
    if not isinstance(config, dict) or not isinstance(config.get("model_list"), list):
        raise HTTPException(422, "configuration.model_list is required")
    if len(config["model_list"]) > 1000:
        raise HTTPException(422, "Too many model deployments")
    if not isinstance(config.get("router_settings", {}), dict):
        raise HTTPException(422, "router_settings must be an object")
    ids = set()
    for entry in config["model_list"]:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("litellm_params"), dict)
            or not isinstance(entry.get("model_info", {}), dict)
        ):
            raise HTTPException(422, "Invalid model deployment")
        params = entry.get("litellm_params", {})
        identifier = entry.get("model_info", {}).get("id")
        if not entry.get("model_name") or not isinstance(params.get("model"), str):
            raise HTTPException(
                422, "Each deployment requires model_name and litellm_params.model"
            )
        if identifier is not None and not isinstance(identifier, str):
            raise HTTPException(422, "Deployment id must be a string")
        if identifier and identifier in ids:
            raise HTTPException(422, "Duplicate deployment id")
        ids.add(identifier)
    return copy.deepcopy(payload)


def make_router(configuration):
    import litellm
    from litellm import Router
    from model_gateway.src.telemetry import model_logger

    litellm.drop_params = False
    litellm.suppress_debug_info = True
    litellm.set_verbose = False
    for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    if model_logger not in litellm.callbacks:
        litellm.callbacks.append(model_logger)

    # No arbitrary callback imports supplied by catalog configuration.
    return Router(
        model_list=configuration["model_list"],
        **{
            key: value
            for key, value in configuration.get("router_settings", {}).items()
            if key
            in {
                "routing_strategy",
                "num_retries",
                "timeout",
                "allowed_fails",
                "cooldown_time",
                "enable_pre_call_checks",
            }
        },
    )


class GatewayState:
    def __init__(self, root, router_factory=make_router):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "active.json"
        self.factory = router_factory
        self.active = None
        self.router = None
        self.previous = None
        if self.path.exists():
            stored = json.loads(self.path.read_text())
            self.active = validate_release(stored["active"])
            self.previous = stored.get("previous")
            self.router = self.factory(self.active["configuration"])

    def status(self):
        return {
            "ok": self.router is not None,
            "ready": self.router is not None,
            "release_id": self.active["release_id"] if self.active else None,
            "version": self.active.get("version") if self.active else None,
        }

    def validate(self, payload):
        release = validate_release(payload)
        self.factory(release["configuration"])
        return {"ok": True, "release_id": release["release_id"]}

    def persist(self, active, previous):
        temporary = self.root / "active.json.tmp"
        with temporary.open("w", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            json.dump({"active": active, "previous": previous}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def activate(self, payload):
        release = validate_release(payload)
        if self.active and self.active["release_id"] == release["release_id"]:
            if self.active != release:
                raise HTTPException(
                    409, "release_id already identifies different configuration"
                )
            return self.status()
        router = self.factory(release["configuration"])
        self.persist(release, self.active)
        self.previous, self.active, self.router = self.active, release, router
        return self.status()

    def rollback(self, release_id):
        if not self.active or self.active["release_id"] != release_id:
            raise HTTPException(409, "Active release changed")
        if not self.previous:
            raise HTTPException(409, "No previous release")
        router = self.factory(self.previous["configuration"])
        self.persist(self.previous, None)
        self.active, self.previous, self.router = self.previous, None, router
        return self.status()
