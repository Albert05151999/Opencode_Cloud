"""Explicit old-installation fixture; production bootstrap stays empty."""
import configparser
import copy
import time
from catalog_service.src.management import identifier, skill_metadata

def populate_legacy(self):
    if self.read()[1].get("agents"):
        return
    with self.edit() as data:
        if data.get("agents"):
            return
        data["bootstrapped"] = True
        for config in sorted(self.agents_root.glob("*/agent.cfg")):
            cfg = configparser.ConfigParser(interpolation=None)
            cfg.read(config, encoding="utf-8")
            aid = cfg["agent"]["id"]
            models = cfg["models"]["allowed"].split(",")
            for mid in models:
                data["models"].setdefault(
                    mid,
                    {
                        "id": mid,
                        "name": mid,
                        "provider": "legacy",
                        "upstream_model": mid,
                        "enabled": False,
                        "legacy": True,
                    },
                )
            bindings = []
            for skill in sorted((config.parent / "skills").glob("*/SKILL.md")):
                meta = skill_metadata(skill.read_bytes())
                rid = identifier(aid + "-" + skill.parent.name)
                files = {
                    p.relative_to(skill.parent).as_posix(): self.blob(
                        p.read_bytes()
                    )
                    for p in skill.parent.rglob("*")
                    if p.is_file() and not p.is_symlink()
                }
                version = {
                    "version": 1,
                    "created": time.time(),
                    "data": meta,
                    "files": files,
                }
                data["resources"][rid] = {
                    "id": rid,
                    "kind": "skill",
                    "name": meta["name"],
                    "owner": aid,
                    "archived": False,
                    "draft": {"data": meta, "files": files},
                    "versions": [version],
                }
                bindings.append({"id": rid, "version": 1})
            draft = {
                "name": cfg["agent"]["display_name"],
                "description": "",
                # Fresh installs retain the bundled Agents and resources,
                # but they cannot run until a configured model is assigned.
                "enabled": False,
                "instructions": (config.parent / "AGENTS.md").read_text(
                    encoding="utf-8"
                ),
                "allowed_model_ids": models,
                "default_model_id": cfg["models"]["default"],
                "small_model_id": None,
                "bindings": bindings,
            }
            data["agents"][aid] = {
                "id": aid,
                "draft": draft,
                "versions": [
                    {
                        "version": 1,
                        "created": time.time(),
                        "config": copy.deepcopy(draft),
                        "path": str(config.parent.resolve()),
                    }
                ],
                "active": 1,
            }
