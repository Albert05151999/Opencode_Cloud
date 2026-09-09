# OpenCode 云端 Agent 平台

当前版本为 0.2.2，包含本地聊天和配置管理页。全新 clone 请先按 [源码构建说明](docs/build-from-source.md) 生成镜像与 Web 包；构建不依赖旧版发布目录或备份。完成前端构建后，可在 Windows 项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-web.ps1
```

默认打开 `http://127.0.0.1:18765/chat`。支持模型导入、Agent 模型分配、MCP 表单、Skill 附件和 Hook 编辑、版本发布与回滚。发布的 Web ZIP 内含编译页面，日常无需 Node.js；源码仓库不提交编译产物。服务器与 Web 使用对应版本，并在连接设置填写管理员凭据。

完整 PowerShell 上传、Ubuntu 部署和使用步骤见 [Web 部署说明](docs/web-readme.md)，规划及完成记录见 [04-user_manager_web.md](04-user_manager_web.md)。交付包位于 `artifacts/release/web-v0.2.2/`，本地 Web 包与服务器离线镜像包分开提供。

远端执行客户端：安装 `httpx` 后运行 `python scripts/sse-chat.py --base-url http://服务器IP:18080`，实时显示远端回答和工具状态。当前工作区客户端已配置本次验证的服务器地址。新部署默认监听 `0.0.0.0:18080`，已有实例可通过安装器 `--host/--port` 显式迁移。离线网络修订包及访问边界见 [网络部署说明](docs/network-release-readme.md)。

当前实现按 `03_zero_to_one_todolist.md` 的顺序推进。架构、API 契约、构建思路和机器可读进度分别位于根目录设计文档、`docs/build-and-verification.md` 与 `docs/progress.json`。

开发控制器环境：

```bash
python3 -m venv .venv-controller
.venv-controller/bin/pip install -e '.[test]'
.venv-controller/bin/python -m pytest
.venv-controller/bin/python -m app.main
```

正式入口会加载 `config.cfg`，组合文件 API、OpenCode 代理、Prometheus 指标和健康/空闲生命周期循环。WSL 中运行时账号为 UID/GID 10001；准备 `/srv/cloud-agent` 的目录权限后启动。模型网关部署与自动验证参见 `docs/model-gateway.md`。`/cloud/health` 检查进程存活，`/cloud/health/ready` 检查 SQLite、Docker、固定镜像、工作区与模型网关。没有运行模型网关时，就绪端点返回 503。
