"""Import-only Agent templates: no Agent exists until an explicit restore action."""

import copy
import json
import time
import uuid

from catalog_service.src.admin_dto import AgentDefinition
from catalog_service.src.management import fail, identifier, redact


def remap_template(template, mappings):
    value = copy.deepcopy(template)
    config = value["config"]
    for field in ("default_model_id", "small_model_id"):
        if config.get(field):
            config[field] = mappings.get(("model", config[field]), config[field])
    config["allowed_model_ids"] = [
        mappings.get(("model", mid), mid) for mid in config["allowed_model_ids"]
    ]
    for binding in config.get("bindings", []):
        binding["id"] = mappings.get(("resource", binding["id"]), binding["id"])
    return value


class AgentTemplates:
    def __init__(self, store):
        self.store = store

    def list(self):
        return list(redact(self.store.read()[1].get("agent_templates", {})).values())

    def restore(self, tid, aid, models=None, resources=None):
        identifier(aid)
        with self.store.edit() as data:
            template = data.get("agent_templates", {}).get(tid)
            if not template:
                fail("Agent template not found", 404)
            if aid in data["agents"] or aid in data.get("agent_tombstones", {}):
                fail("Choose an unused Agent ID", 409)
            cfg = copy.deepcopy(template["config"])
            model_map = models or {}
            cfg["allowed_model_ids"] = [
                model_map.get(mid, mid) for mid in cfg["allowed_model_ids"]
            ]
            cfg["default_model_id"] = model_map.get(
                cfg["default_model_id"], cfg["default_model_id"]
            )
            if cfg.get("small_model_id"):
                cfg["small_model_id"] = model_map.get(
                    cfg["small_model_id"], cfg["small_model_id"]
                )
            for binding in cfg["bindings"]:
                selected = (resources or {}).get(binding["id"])
                if selected:
                    binding.update(id=selected["id"], version=selected["version"])
                elif template.get("imported"):
                    # Imported immutable versions are separate global drafts.
                    # Administrators must publish them before restoring a template.
                    binding["version"] = 1
            cfg = AgentDefinition.model_validate(cfg).model_dump()
            self.store.validate_agent(data, aid, cfg)
            data["agents"][aid] = {
                "id": aid,
                "draft": cfg,
                "active": None,
                "versions": [],
            }
            template["last_restored"] = {"agent_id": aid, "at": time.time()}
        return {"agent_id": aid, "published": False}
