"""Disposable Docker validation; never executes hooks in controller process."""

import asyncio
import copy
import json
import os
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
import httpx
from shared_libs.validation import fail


class ProbeRunner:
    def __init__(self, backend, client, root):
        self.backend, self.client = backend, client
        self.store = SimpleNamespace(
            root=Path(root), file=lambda x: x, blob=lambda x: x
        )

    async def probe(self, path, *, mcp=False):
        """A disposable, unprivileged runtime with separate workspace and state."""
        config = self.backend.config
        probe_id = "probe_" + uuid.uuid4().hex
        temp = self.store.root / "probes" / probe_id
        temp.mkdir(parents=True)
        log_root = Path(os.environ.get("HOST_LOG_ROOT", str(self.store.root / "log")))
        runtime_log = log_root / "agent_runtime" / probe_id
        runtime_log.mkdir(parents=True)
        for directory in (temp / "workspace", temp / "state", runtime_log):
            directory.mkdir(exist_ok=True)
            if os.geteuid() == 0:
                os.chown(directory,10001,10001)
            directory.chmod(0o755)
        port_number = config.sandbox.opencode_internal_port
        environment = {"SANDBOX_ID":probe_id,"RUNTIME_LOG_DIR":"/runtime-log","OPENCODE_PORT":str(port_number)}
        if os.environ.get("MODEL_GATEWAY_TOKEN"):
            environment["MODEL_GATEWAY_TOKEN"] = os.environ["MODEL_GATEWAY_TOKEN"]
        container = None
        try:
            container = await asyncio.to_thread(
                self.backend.client.containers.run,
                config.sandbox.image,
                detach=True,
                name="cloud-" + probe_id,
                environment=environment,
                user="10001:10001",
                read_only=True,
                labels={"cloud.management_probe": config.platform.instance_id},
                tmpfs={"/tmp": "rw,nosuid,nodev,size=256m"},
                mem_limit="1g",
                pids_limit=256,
                nano_cpus=1_000_000_000,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                volumes={
                    str(path): {"bind": "/opt/agent", "mode": "ro"},
                    str(runtime_log): {"bind": "/runtime-log", "mode": "rw"},
                    str(temp / "workspace"): {"bind": "/workspace", "mode": "rw"},
                    str(temp / "state"): {"bind": "/state/opencode", "mode": "rw"},
                },
                extra_hosts={"host.docker.internal": "host-gateway"},
                ports={f"{port_number}/tcp": ("127.0.0.1", None)},
            )
            await asyncio.to_thread(container.reload)
            port = container.attrs["NetworkSettings"]["Ports"][f"{port_number}/tcp"][0][
                "HostPort"
            ]
            url = "http://127.0.0.1:" + port
            deadline = time.monotonic() + config.sandbox.start_timeout_seconds
            while time.monotonic() < deadline:
                await asyncio.to_thread(container.reload)
                if container.attrs.get("State",{}).get("Status") in {"exited","dead"}:
                    fail("Isolated runtime exited before readiness; inspect probe startup evidence",422)
                try:
                    response = await self.client.get(url + "/global/health", timeout=2)
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.5)
            else:
                fail(
                    "Isolated runtime did not start; check Hook syntax and runtime dependencies",
                    422,
                )
            response = await self.client.get(url + "/config", timeout=20)
            response.raise_for_status()
            if mcp:
                response = await self.client.get(url + "/mcp", timeout=120)
                response.raise_for_status()
                states = response.json()
                if any(v.get("status") != "connected" for v in states.values()):
                    # Provider errors can echo credential URLs; keep diagnostics categorical.
                    return {
                        "ok": False,
                        "mcp": {
                            k: {
                                "status": v.get("status"),
                                "error": "Check URL, credentials, installed executable and timeout",
                            }
                            for k, v in states.items()
                        },
                    }
                tools = await self.client.get(
                    url + "/experimental/tool/ids", timeout=15
                )
                return {
                    "ok": True,
                    "mcp": states,
                    "tools": tools.json() if tools.status_code == 200 else [],
                }
            return {"ok": True}
        except httpx.HTTPError:
            fail("Runtime probe failed; check extension configuration", 422)
        finally:
            if container:
                await asyncio.to_thread(container.reload)
                state = container.attrs.get("State",{})
                evidence = {"probe_id":probe_id,"container_id":container.id,"image":config.sandbox.image,
                            "state":{key:state.get(key) for key in ("Status","ExitCode","OOMKilled")},
                            "start_timeout_seconds":config.sandbox.start_timeout_seconds,
                            "bind_sources":[str(path),str(temp / "workspace"),str(temp / "state"),str(runtime_log)]}
                (runtime_log / "probe-evidence.json").write_text(json.dumps(evidence,indent=2)+"\n")
                await asyncio.to_thread(container.remove, force=True)

    async def compile_hook(self, draft):
        directory = self.store.root / "hook-checks" / uuid.uuid4().hex
        directory.mkdir(parents=True)
        directory.chmod(0o755)
        for p, digest in draft["files"].items():
            destination = directory / p
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(self.store.file(digest))
        # node:module strips TypeScript without evaluating source. Validation is inside
        # an unprivileged, network-disabled container; stdout is captured, never logged.
        compiler = r"""
import fs from 'node:fs'; import path from 'node:path'; import {stripTypeScriptTypes} from 'node:module';
import {spawnSync} from 'node:child_process';
const root='/source'; const result={};
function visit(dir){for(const n of fs.readdirSync(dir)){const p=path.join(dir,n); if(fs.statSync(p).isDirectory())visit(p); else {
const relative=path.relative(root,p); let code=fs.readFileSync(p,'utf8');
if(p.endsWith('.ts'))code=stripTypeScriptTypes(code,{mode:'transform'});
if(/\brequire\s*\(|\bimport\s*\(/.test(code))throw Error('Dynamic imports are unsupported');
for(const m of code.matchAll(/(?:from\s*|import\s*)['"]([^'"]+)['"]/g)){
const id=m[1]; if(!id.startsWith('node:')&&!id.startsWith('./')&&!id.startsWith('../'))throw Error('External dependencies are unsupported');
if(id.startsWith('.')){const resolved=path.resolve(path.dirname(p),id);if(!resolved.startsWith(root+'/')||!fs.existsSync(resolved))throw Error('Invalid relative import');}}
const check=spawnSync(process.execPath,['--input-type=module','--check'],{input:code,encoding:'utf8'});
if(check.status!==0)throw Error('Invalid JavaScript/TypeScript syntax'); result[relative]=code;
}}} try{visit(root);process.stdout.write(JSON.stringify({files:result}));}catch(e){process.stdout.write(JSON.stringify({error:e.message}));process.exitCode=1;}
"""
        container = None
        try:
            container = await asyncio.to_thread(
                self.backend.client.containers.create,
                self.backend.config.sandbox.image,
                entrypoint=["node", "--input-type=module", "-e"],
                command=[compiler],
                user="10001:10001",
                network_disabled=True,
                read_only=True,
                mem_limit="256m",
                pids_limit=64,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                volumes={str(directory): {"bind": "/source", "mode": "ro"}},
            )
            await asyncio.to_thread(container.start)
            status = await asyncio.to_thread(container.wait, timeout=30)
            result = json.loads(
                await asyncio.to_thread(container.logs, stdout=True, stderr=False)
            )
            if status["StatusCode"] or result.get("error"):
                fail(result.get("error", "Hook static validation failed"), 422)
            checked = copy.deepcopy(draft)
            # Keep .ts extension: pinned OpenCode/Bun loads stripped JS from it too.
            checked["files"] = {
                p: self.store.blob(code.encode()) for p, code in result["files"].items()
            }
            return checked
        finally:
            if container:
                await asyncio.to_thread(container.remove, force=True)
