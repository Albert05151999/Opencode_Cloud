# Development environment

Validated reset target: `Ubuntu-24.04`, WSL2, Ubuntu 24.04.4 LTS, x86_64.
Windows workspace: `E:\Project_Space\Opencode_Cloud`.
Linux development directory: `/home/zephyrusg14/projects/cloud-agent` (currently empty).

The reset in this session was explicitly authorized after inventory. Back up and verify existing data before any future reset. Commands executed after successful export verification:

```powershell
wsl --shutdown
wsl --unregister Ubuntu-24.04
wsl --install -d Ubuntu-24.04 --no-launch --version 2
wsl -d Ubuntu-24.04 -u root -- bash -lc 'useradd --create-home --shell /bin/bash --groups sudo zephyrusg14; mkdir -p /home/zephyrusg14/projects/cloud-agent; chown -R zephyrusg14:zephyrusg14 /home/zephyrusg14/projects'
wsl --manage Ubuntu-24.04 --set-default-user zephyrusg14
```

The developer account has no password set. Provisioning uses explicit `wsl -u root`; no passwordless sudo rule was added. To set an interactive sudo password when needed, run `wsl -d Ubuntu-24.04 -u root -- passwd zephyrusg14` yourself.

Run baseline provisioning:

```powershell
wsl -d Ubuntu-24.04 -u root -- bash /mnt/e/Project_Space/Opencode_Cloud/scripts/setup-ubuntu.sh
```

Evidence lives under `artifacts/env/`; authoritative task status is in `docs/progress.json`. The full pre-reset backup remains under the ignored `artifacts/env/backups/` directory.

## Runtime baseline

Node 24.20.0 and OpenCode 1.18.29 are recorded in `versions.env`. Run `scripts/install-node.sh` and `scripts/install-opencode.sh` as WSL root, then `scripts/verify-node.sh` and `scripts/verify-opencode.py` as the development user. Node uses the official Linux x64 archive and upstream SHA-256 checksums. Linux executables must resolve under `/usr/local/bin`; WSL also inherits Windows executable paths.

OpenCode `/doc` was observed to return JSON (OpenAPI 3.1.0, 162 paths), saved as `artifacts/opencode/openapi.json`. The earlier `.html` example in the development checklist was corrected to match the actual response.

## WSL 与 Docker 网络

该机器的 Windows HTTP 代理监听 `127.0.0.1:7897`。WSL NAT 模式无法访问 Windows loopback，表现为 WSL 启动警告、Docker 官方仓库 TLS 重置以及 Docker Hub 超时。已在 `%UserProfile%/.wslconfig` 应用 `config/wslconfig.example` 中的 mirrored networking、自动代理与 DNS tunneling 设置，并经 `wsl --shutdown` 后验证 WSL 能收到代理环境变量。

Docker Engine 作为 systemd 服务不会继承交互 shell 的代理。开发环境使用 `scripts/configure-docker-proxy.sh http://127.0.0.1:7897` 创建 daemon drop-in。这个端口是机器配置，不能烘焙进发布镜像；部署脚本应将可选代理作为显式配置并由 `doctor.sh` 验证连通性。

The initial supported LSP set is empty (`lsp: false`); shell/Python tooling remains available. There are no configured platform plugins yet. Model provider configuration will be added in the model gateway phase. The controlled config restricts provider selection to the future `cloud-model-gateway` provider, disables sharing and updates, and the entrypoint sets the four required no-download flags. These settings follow the [OpenCode configuration documentation](https://opencode.ai/docs/config/) and are checked against the running pinned server.

`scripts/verify-opencode.py --stabilized` starts with new HOME/XDG directories, traces network syscalls, calls health, observes another 10 seconds, and fails on any INET connect/send destination. Its scope is startup only; it does not establish model/tool behavior or Docker read-only compatibility. `--config-check` separately verifies the effective upstream config. A TIME_WAIT socket initially caused the port preflight to fail despite no listener; SO_REUSEADDR fixed the preflight, and the traced probe passed afterward.

OpenCode 1.18.29 的镜像级只读测试确认：仅设置 `XDG_DATA_HOME` 仍会尝试创建 `$HOME/.local`。运行时因此把 `HOME`、`XDG_DATA_HOME` 和 `XDG_CONFIG_HOME` 都定向到 `/state/opencode` 下的持久化子目录。这是对固定上游版本行为的实测修正，不能删掉后只依赖 XDG 假设。
