import asyncio, base64, copy, configparser, json, os, re, shutil, time, uuid
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse
import httpx
from .management import fail, redact
from .agents import AgentCatalog


class Compiler:
    def __init__(self, store, config):
        self.store = store
        self.backend = SimpleNamespace(config=config)
        self.blocked = set()

    def authorize(self, agent_id, method, path, payload):
        _, data = self.store.read()
        agent = data["agents"].get(agent_id)
        if not agent:
            fail("Unknown Agent", 404)
        if agent.get("lifecycle") == "deleting":
            fail("Agent deletion is pending; inspect the operation result", 409)
        active = self.store.agent_config(agent)
        if not active:
            fail("Publish this Agent before starting a session", 409)
        mutation = method not in {"GET", "HEAD", "OPTIONS", "DELETE"}
        abort = path.endswith("/abort")
        response = bool(
            re.search(
                r"/(?:permissions/[^/]+|permission/[^/]+/reply|question/[^/]+/(?:reply|reject))$",
                path,
            )
        )
        if agent_id in self.blocked and not abort and not response:
            fail("Agent configuration is being applied; retry shortly", 503)
        if mutation and not abort and not response:
            if agent_id in self.blocked:
                fail("Agent configuration is being applied; retry shortly", 503)
            if agent.get("lifecycle") == "archived":
                fail("Agent is archived; restore it before generating", 409)
            if any(
                j["status"] in {"queued", "validating", "waiting", "applying"}
                and j["target"] == agent_id
                and j["kind"].startswith(
                    ("sandbox.", "agent.archive", "agent.restore", "agent.delete")
                )
                for j in data["jobs"].values()
            ):
                fail(
                    "An operation is pending for this Agent; retry after completion",
                    409,
                )
            if not active.get("enabled", True):
                fail("Agent is disabled; history remains available", 409)
            if hasattr(self, "operations"):
                self.operations.recovery.invalidate_idle(agent_id)
        # Platform-managed provider configuration must not be bypassed by native writes.
        if method not in {"GET", "HEAD", "OPTIONS"} and (
            path in {"config", "global/config"}
            or path.startswith(("auth/", "mcp/", "provider/"))
        ):
            fail("Use the versioned management API for configuration changes", 403)
        if (
            isinstance(payload, dict)
            and mutation
            and re.search(
                r"/session/[^/]+/(message|prompt_async|command|shell)$", "/" + path
            )
            and not payload.get("model")
        ):
            chosen = {
                "providerID": "cloud-model-gateway",
                "modelID": active["default_model_id"],
            }
            payload["model"] = (
                "cloud-model-gateway/" + active["default_model_id"]
                if path.endswith("/command")
                else chosen
            )
        model = payload.get("model") if isinstance(payload, dict) else None
        if (
            not model
            and isinstance(payload, dict)
            and ("providerID" in payload or "modelID" in payload)
        ):
            model = {
                "providerID": payload.get("providerID"),
                "modelID": payload.get("modelID"),
            }
        if model:
            if isinstance(model, str):
                provider, _, mid = model.partition("/")
            elif isinstance(model, dict):
                provider, mid = model.get("providerID"), model.get("modelID")
            else:
                fail("Invalid model selection")
            if (
                provider != "cloud-model-gateway"
                or mid not in active["allowed_model_ids"]
            ):
                fail("Model is not assigned to this Agent", 403)
        return mutation and not abort and not response

    def compile_agent(self, data, aid, cfg, version, *, preview=False):
        self.store.validate_agent(data, aid, cfg)
        root = self.store.root / "compiled" / (uuid.uuid4().hex) / aid
        if not preview:
            root.mkdir(parents=True)
            root.chmod(0o755)
            for p in ("global/opencode", "skills", "plugins"):
                (root / p).mkdir(parents=True, exist_ok=True)
            (root / "global/opencode/.gitignore").write_text("*\n")
            trace = (
                Path(__file__).parents[1]
                / "resources/agents/agent-code/plugins/trace.mjs"
            )
            shutil.copyfile(trace, root / "plugins/system-trace.mjs")
            (root / "AGENTS.md").write_text(
                cfg.get("instructions", ""), encoding="utf-8"
            )
        plugin = ["file:///opt/agent/plugins/system-trace.mjs"]
        mcp, sources = {}, []
        for binding in cfg["bindings"]:
            resource, rv = self.store.resource_version(
                data, binding["id"], binding["version"]
            )
            name = rv["data"].get("name", resource["name"])
            source = {
                "id": resource["id"],
                "owner": resource["owner"],
                "kind": resource["kind"],
                "name": name,
                "version": rv["version"],
            }
            if resource["kind"] == "mcp":
                mcp[name] = copy.deepcopy(rv["data"])
                cwd = mcp[name].pop("cwd", None)
                if cwd and mcp[name]["type"] == "local":
                    # OpenCode's native local MCP has no cwd field. Change it only
                    # in the sandbox child process, without shell interpolation.
                    mcp[name]["command"] = [
                        "python3",
                        "-c",
                        "import os,sys; os.chdir(sys.argv[1]); os.execvp(sys.argv[2],sys.argv[2:])",
                        cwd,
                        *mcp[name]["command"],
                    ]
                source["path"] = "mcp." + name
            else:
                directory = (
                    "skills/" if resource["kind"] == "skill" else "plugins/"
                ) + resource["id"]
                if not preview:
                    for relative, digest in rv["files"].items():
                        dest = root / directory / relative
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(self.store.file(digest))
                        dest.chmod(0o644)
                source["path"] = "/opt/agent/" + directory
                if resource["kind"] == "hook":
                    plugin.append(
                        "file:///opt/agent/"
                        + directory
                        + "/"
                        + rv["data"].get("compiled_entry", rv["data"]["entry"])
                    )
            sources.append(source)
        models = {}
        for mid in cfg["allowed_model_ids"]:
            model = data["models"][mid]
            models[mid] = {"name": model.get("name", mid)}
            if model.get("context") and model.get("output"):
                models[mid]["limit"] = {
                    "context": model["context"],
                    "output": model["output"],
                }
        gateway_port = urlparse(self.backend.config.model_gateway.base_url).port or 80
        opencode = {
            "$schema": "https://opencode.ai/config.json",
            "share": "disabled",
            "autoupdate": False,
            "lsp": False,
            "permission": "allow",
            "plugin": plugin,
            "instructions": ["/opt/agent/AGENTS.md"],
            "skills": {"paths": ["/opt/agent/skills"]},
            "mcp": mcp,
            "enabled_providers": ["cloud-model-gateway"],
            "model": "cloud-model-gateway/" + cfg["default_model_id"],
            "provider": {
                "cloud-model-gateway": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Cloud Model Gateway",
                    "options": {
                        "baseURL": self.backend.config.model_gateway.base_url,
                        "apiKey": "{env:MODEL_GATEWAY_TOKEN}",
                    },
                    "models": models,
                }
            },
        }
        if cfg.get("small_model_id"):
            opencode["small_model"] = "cloud-model-gateway/" + cfg["small_model_id"]
        if preview:
            return {"opencode": redact(opencode), "sources": sources}
        (root / "opencode.json").write_text(
            json.dumps(opencode, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        config = self.backend.config
        ini = configparser.ConfigParser(interpolation=None)
        ini["agent"] = {
            "id": aid,
            "display_name": cfg["name"],
            "image": config.sandbox.image,
            "idle_timeout_seconds": str(config.sandbox.idle_timeout_seconds),
        }
        ini["resources"] = {
            "cpu_limit": str(config.sandbox.default_cpu),
            "memory_mb": str(config.sandbox.default_memory_mb),
            "pids_limit": str(config.sandbox.default_pids),
        }
        ini["models"] = {
            "default": cfg["default_model_id"],
            "allowed": ",".join(cfg["allowed_model_ids"]),
        }
        with (root / "agent.cfg").open("w", encoding="utf-8") as stream:
            ini.write(stream)
        (root / "effective.json").write_text(
            json.dumps(
                {"version": version, "sources": sources, "config": redact(opencode)},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        AgentCatalog(
            root.parent, gateway_url=self.backend.config.model_gateway.base_url
        ).load(aid)
        return root

    def gateway_configuration(self, models, environment):
        entries = []
        for model in models.values():
            if not model.get("enabled", True):
                continue
            mid = model["id"]
            if model.get("legacy"):
                prefix = mid.upper().replace("-", "_")
                if prefix + "_MODEL" not in environment:
                    fail("Original gateway environment is missing model " + mid)
                for index in (1, 2):
                    entries.append(
                        {
                            "model_name": mid,
                            "litellm_params": {
                                "model": environment[prefix + "_MODEL"],
                                "api_base": environment[prefix + f"_{index}_API_BASE"],
                                "api_key": environment[prefix + "_API_KEY"],
                            },
                            "model_info": {"id": mid + "-" + str(index)},
                        }
                    )
            else:
                prefix = {
                    "openai-compatible": "openai",
                    "openai": "openai",
                    "anthropic": "anthropic",
                    "google": "gemini",
                }[model["provider"]]
                params = {
                    "model": prefix + "/" + model["upstream_model"],
                    "api_key": model.get("api_key", ""),
                    **model.get("parameters", {}),
                }
                if model.get("base_url"):
                    params["api_base"] = model["base_url"]
                if model.get("headers"):
                    params["extra_headers"] = model["headers"]
                entries.append(
                    {
                        "model_name": mid,
                        "litellm_params": params,
                        "model_info": {"id": mid},
                    }
                )
                for index, base in enumerate(model.get("additional_base_urls", []), 1):
                    entries.append(
                        {
                            "model_name": mid,
                            "litellm_params": {**params, "api_base": base},
                            "model_info": {"id": mid + "-extra-" + str(index)},
                        }
                    )
        return {
            "model_list": entries,
            "router_settings": {
                "routing_strategy": "least-busy",
                "num_retries": 2,
                "timeout": 600,
                "allowed_fails": 1,
                "cooldown_time": 30,
            },
            "litellm_settings": {
                "callbacks": ["prometheus", "cloud_logging.cloud_logger"],
                "drop_params": False,
            },
            "general_settings": {"disable_spend_logs": True},
        }
