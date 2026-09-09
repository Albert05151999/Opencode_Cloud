# OpenCode 云端 Agent 平台 — 0→1 开发与验证待办事项

> 执行方式：本文档旨在直接用作 MainAgent 的任务清单。  
> 开发主机：Windows + VS Code + Codex 插件。  
> Linux 环境：WSL2 Ubuntu 24.04。  
> 主要代码语言：Python。  
> 最终本地验收：两个示例 Agent，每个支持两个逻辑模型，每个 Agent 处理 4 个并发请求；同时运行两个 Agent，形成 8 请求突发负载，并报告 TTFT/延迟/资源指标。  
> 最终发布物：可移植的 Linux 发布包，其中包含固定版本的镜像、部署脚本以及健康检查/监控配置。

---

# 0. MainAgent 运行规则

## 0.1 MainAgent 职责

- [ ] 将本文档作为有序的唯一事实来源。
- [ ] 在 `docs/progress.json` 中维护机器可读的进度文件。
- [ ] 开始任务前，记录 `status=running`、负责的子 Agent、预期输出和验证命令。
- [ ] 任务完成后，MainAgent 必须独立运行验证；不得把子 Agent 的陈述当作证明。
- [ ] 仅在通过验证关卡后提交。
- [ ] 如果关卡失败，先修复当前阶段再继续推进。
- [ ] 不得暗中更改 `01_architecture.md` 中的架构决策。
- [ ] 除非 MainAgent 先记录一个阻塞项，证明上游接口无法满足必需功能，否则不要修改 OpenCode 源代码。
- [ ] 优先采用小而可用的实现，而不是通用化框架。
- [ ] V1 中不要添加 Kubernetes、Redis、PostgreSQL、服务网格、Kata、分布式调度或自定义模型负载均衡器。

## 0.2 建议的子 Agent

仅当它们的工作不会并发编辑相同文件时才创建。

| 子 Agent | 范围 |
|---|---|
| `env-agent` | WSL/Linux 前置条件和可复现环境脚本 |
| `runtime-agent` | Node/OpenCode/Python 运行时和 Agent 基础镜像 |
| `controller-agent` | FastAPI 网关、路由、SQLite 注册表、Docker 沙箱管理器 |
| `model-agent` | LiteLLM 配置、模型路由、模型指标 |
| `storage-agent` | 工作区布局、上传/下载、路径验证 |
| `observability-agent` | Prometheus 指标、健康检查、仪表板/配置 |
| `test-agent` | 集成测试、SSE 测试、负载测试、TTFT 测量 |
| `release-agent` | 打包、doctor/install/start/stop 脚本、发布可复现性 |

MainAgent 最多可同时运行 3 个相互独立的子 Agent。根据用户指示，子 Agent 使用 GPT-5.6 和低思考强度；MainAgent 负责架构决策和独立验证。

## 0.3 必需的证据格式

每个已完成任务都必须记录：

```text
Task ID:
Files changed:
Commands executed:
Observed output:
Pass/fail:
Known limitations:
Next task unlocked:
```

---

# 1. 重置并重新创建 WSL 开发环境

> `wsl --unregister` 会删除所选发行版及其中的全部数据。MainAgent 必须先确认目标发行版中没有遗留任何重要内容。

## 1.1 清点与备份关卡

- [x] 在 Windows PowerShell 中运行：

```powershell
wsl -l -v
```

- [x] 确认目标发行版正是 `Ubuntu-24.04`。
- [x] 导出或复制所有必须保留的源代码/数据。
- [x] 记录当前 Windows/WSL 版本：

```powershell
wsl --version
wsl --status
```

### 验证关卡

- [x] MainAgent 输出发行版列表以及将要重置的确切发行版。
- [x] MainAgent 记录备份已完成，或该发行版不含所需数据。

## 1.2 仅重置 Ubuntu

- [x] 停止 WSL：

```powershell
wsl --shutdown
```

- [x] 仅移除目标 Ubuntu 发行版：

```powershell
wsl --unregister Ubuntu-24.04
```

- [x] 使用 Windows 机器上可用的常规 WSL 安装方式重新安装 Ubuntu 24.04。
- [x] 确保使用 WSL2：

```powershell
wsl -l -v
```

### Verification gate

- [x] `Ubuntu-24.04` 存在。
- [x] VERSION 列为 `2`。
- [x] Ubuntu shell 可成功打开。
- [x] 已记录 `uname -a` 和 `/etc/os-release`。

---

# 2. 建立干净的 Ubuntu 基线

## 2.1 更新基础系统

- [x] 在 Ubuntu 内运行：

```bash
sudo apt update
sudo apt upgrade -y
```

- [x] 安装最基本的开发工具：

```bash
sudo apt install -y \
  ca-certificates curl wget git jq unzip zip zstd \
  build-essential pkg-config make gcc g++ \
  python3 python3-venv python3-pip \
  sqlite3 strace lsof iproute2 net-tools
```

- [x] 设置/创建项目根目录，例如：

```bash
mkdir -p ~/projects/cloud-agent
cd ~/projects/cloud-agent
```

### Verification gate

```bash
git --version
curl --version
python3 --version
sqlite3 --version
strace -V
```

- [x] 所有命令均成功返回。
- [x] 将输出保存到 `artifacts/env/ubuntu-baseline.txt`。

---

# 3. 安装并验证 Node.js

当前设计目标：Node.js 24 LTS。在设计时，Node 24 是当前 LTS 版本线；发布时需固定经过测试的确切补丁版本。

## 3.1 开发环境安装

- [x] 使用可复现的版本管理器或官方 Node 发行包安装 Node 24。
- [x] 最终镜像中不要使用未固定版本的 Current 发行版。

推荐的 nvm WSL 开发流程：

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.7/install.sh | bash
. "$HOME/.nvm/nvm.sh"
nvm install 24
nvm alias default 24
```

## 3.2 验证

```bash
node --version
npm --version
which node
which npm
```

### Verification gate

- [x] 主版本号为 24。
- [x] 一个简单的 Node 脚本执行成功：

```bash
node -e 'console.log("node-ok", process.version)'
```

- [x] 记录通过测试的确切补丁版本。

---

# 4. 安装并固定 OpenCode 版本

OpenCode 官方支持通过 npm 安装，并建议在 Windows 上使用 WSL。

## 4.1 查找候选版本

- [x] 仅在构建/开发阶段查询软件包版本：

```bash
npm view opencode-ai version
```

- [x] 将确切候选版本保存到：

```text
versions.env
```

格式示例：

```text
NODE_VERSION=<exact-tested-version>
OPENCODE_VERSION=<exact-tested-version>
PYTHON_VERSION=<observed-version>
```

## 4.2 安装确切版本的 OpenCode

```bash
npm install -g opencode-ai@${OPENCODE_VERSION}
```

## 4.3 验证 CLI

```bash
opencode --version
which opencode
```

## 4.4 验证服务器

- [x] 创建一个临时空工作区。
- [x] 启动：

```bash
opencode serve --hostname 127.0.0.1 --port 4096
```

- [x] 在另一个 shell 中：

```bash
curl -fsS http://127.0.0.1:4096/global/health | jq
curl -fsS http://127.0.0.1:4096/doc > artifacts/opencode/openapi.json
```

### Verification gate

- [x] `/global/health` 报告健康。
- [x] 报告的 OpenCode 版本与固定版本完全一致。
- [x] `/doc` 可访问。
- [x] 在将确切版本写入项目配置前不要继续。

---

# 5. 稳定 OpenCode 启动并消除非必要的启动联网行为

目标：沙箱启动不得依赖软件包注册表、模型目录、更新服务或动态插件下载。

## 5.1 创建受控的 Agent 全局配置

- [x] 创建 `runtime/opencode/global/opencode.json`。
- [x] 禁用会话共享。
- [x] 仅配置必需的提供商/模型。
- [x] 不在运行时配置中使用远程 npm 插件。
- [x] 优先使用随 Agent 目录一同提供的本地插件。

## 5.2 设置运行时环境标志

至少使用：

```bash
export OPENCODE_DISABLE_AUTOUPDATE=1
export OPENCODE_DISABLE_MODELS_FETCH=1
export OPENCODE_DISABLE_DEFAULT_PLUGINS=1
export OPENCODE_DISABLE_LSP_DOWNLOAD=1
```

- [x] 将这些变量放入容器入口点/环境中，不要依赖开发者手动导出。

## 5.3 防止启动时安装插件

- [x] 搜索所有配置中引用 npm 软件包的 `plugin` 条目。
- [x] 将所需的平台插件替换为本地插件文件或构建时预安装的依赖项。
- [x] 如果本地插件需要 npm 依赖项，在镜像构建时安装/缓存它们，并证明启动时不会执行外部软件包下载。

OpenCode 的插件文档说明，npm 插件和本地插件依赖项可能会在启动时自动安装，因此这一关卡是确保启动时间确定性的必要条件。

## 5.4 预安装支持的 LSP 或禁用下载

- [x] 确定 V1 支持的语言服务器集合。
- [x] 对于常见的 Python/TypeScript 支持，仅预安装两个示例 Agent 实际需要的语言服务器。
- [x] 在运行时保持 `OPENCODE_DISABLE_LSP_DOWNLOAD=1`。

## 5.5 启动网络跟踪

- [x] 在 `strace` 下启动 OpenCode：

```bash
mkdir -p artifacts/opencode
strace -f -e trace=network -o artifacts/opencode/startup-network.trace \
  env \
  OPENCODE_DISABLE_AUTOUPDATE=1 \
  OPENCODE_DISABLE_MODELS_FETCH=1 \
  OPENCODE_DISABLE_DEFAULT_PLUGINS=1 \
  OPENCODE_DISABLE_LSP_DOWNLOAD=1 \
  opencode serve --hostname 127.0.0.1 --port 4096
```

- [x] 仅访问 `/global/health`。
- [x] 停止服务器。
- [x] 检查跟踪记录中是否存在意外的公网连接尝试。

### Verification gate

- [x] 使用预期的环境开关可成功启动。
- [x] 不发生意外的 npm/插件/更新/模型目录下载。
- [x] 共享已禁用。
- [x] `/global/health` 仍然成功。
- [x] 继续之前明确记录所有无法避免的网络行为。

---

# 6. 安装并验证 Python 分析/办公基线

开发期间使用项目 venv，并将通过测试的软件包集合构建到运行时镜像中。

## 6.1 创建 venv

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel
```

## 6.2 安装基线软件包

```bash
pip install \
  numpy \
  pandas \
  matplotlib \
  openpyxl \
  xlsxwriter \
  python-pptx \
  python-docx \
  pillow \
  pyyaml \
  markdown \
  tabulate \
  requests \
  httpx
```

在实际 Agent 需要之前，不要添加大型机器学习/科学计算软件包。

## 6.3 验证导入

```bash
python - <<'PY'
import numpy, pandas, matplotlib
import openpyxl, xlsxwriter
import pptx, docx
import PIL, yaml, markdown, tabulate
import requests, httpx
print("python-runtime-ok")
PY
```

## 6.4 功能冒烟测试

- [x] 使用 `openpyxl` 创建一个小型 `.xlsx` 文件。
- [x] 使用 `pandas` 读取它。
- [x] 使用 `python-pptx` 创建一个单页 `.pptx` 文件。
- [x] 渲染/保存一个小型 matplotlib PNG。
- [x] 解析并转储一个 YAML 文件。

### Verification gate

- [x] 所有产物均生成在 `artifacts/python-smoke/` 下。
- [x] 所有导入/功能测试均通过。

---

# 7. 安装 Docker 并验证基础容器运行时

## 7.1 选择一种 WSL Docker 模式

选择以下一种：

- Docker Desktop WSL 集成；或
- 直接安装在 Ubuntu WSL 内的 Docker Engine。

不要在同一本地测试环境中保留两个相互竞争的守护进程。

## 7.2 验证

```bash
docker version
docker info
docker run --rm hello-world
```

### Verification gate

- [x] 可从 WSL 开发 shell 访问 Docker Engine。
- [x] 默认运行时最终使用 runc。
- [x] 容器能够成功启动和退出。

---

# 8. 构建确定性的 Agent 运行时镜像

## 8.1 创建镜像布局

```text
runtime/
├── Dockerfile
├── entrypoint.sh
├── requirements.txt
├── opencode/
│   └── global/
└── smoke/
```

## 8.2 镜像要求

- [x] 以 Ubuntu 24.04 为基础。
- [x] 使用确切的 Node 24 补丁版本，或采用等效的固定版本可复现 Node 安装方式。
- [x] 使用确切的 OpenCode 版本。
- [x] Python 3 + 已测试的软件包。
- [x] Agent 工作流所需的 git/curl/jq/基础构建工具。
- [x] 运行时不安装软件包。
- [x] 在兼容情况下使用非 root 运行时用户。
- [x] 以 `opencode serve --hostname 0.0.0.0 --port 4096` 作为服务入口点。

## 8.3 运行时环境

构建时写入/设置：

```text
OPENCODE_DISABLE_AUTOUPDATE=1
OPENCODE_DISABLE_MODELS_FETCH=1
OPENCODE_DISABLE_DEFAULT_PLUGINS=1
OPENCODE_DISABLE_LSP_DOWNLOAD=1
```

使用 Agent 挂载的配置路径，避免基础镜像配置发生漂移。

## 8.4 构建

```bash
docker build -t cloud-agent-runtime:dev runtime/
```

## 8.5 先测试正常运行模式

- [x] 创建临时挂载目录：

```text
/tmp/cloud-agent-test/workspace
/tmp/cloud-agent-test/state
/tmp/cloud-agent-test/agent
```

- [x] 将有效的测试 Agent `opencode.json` 放入 Agent 挂载目录。
- [x] 运行容器并将端口 4096 发布到 localhost。
- [x] 验证 `/global/health`。

## 8.6 测试生产式只读 rootfs

运行等效于：

```text
--read-only
--tmpfs /tmp
-v <workspace>:/workspace:rw
-v <state>:/state/opencode:rw
-v <agent-config>:/opt/agent:ro
```

### Verification gate

- [x] OpenCode 可在 rootfs 只读时启动。
- [x] 只能在配置的状态挂载目录下持久化所需状态。
- [x] 可以写入 `/workspace` 和 `/tmp`。
- [x] 无法修改 `/opt/agent` 或系统文件。
- [x] 重启后保留工作区和所需的 OpenCode 状态。
- [x] 记录镜像大小。

---

# 9. 创建仓库骨架

采用精简的模块结构：

```text
cloud-agent/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── gateway.py
│   ├── sandbox.py
│   ├── registry.py
│   ├── workspace.py
│   ├── models.py
│   ├── metrics.py
│   └── errors.py
├── agents/
│   ├── agent-code/
│   └── agent-data/
├── runtime/
├── deploy/
├── monitoring/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── load/
├── docs/
│   ├── progress.json
│   └── upstream/
├── config.cfg
├── pyproject.toml
└── README.md
```

### Verification gate

- [x] `python -m pytest` 可运行一个简单测试。
- [x] `python -m app.main` 可启动占位健康检查端点。

---

# 10. 优先实现 `config.cfg`

## 10.1 实现 `app/config.py`

- [x] 使用 `configparser` 读取 INI 格式的 `config.cfg`。
- [x] 解析 int/float/bool/list 值。
- [x] 支持环境变量覆盖语法：

```text
CLOUD_AGENT__SECTION__KEY
```

- [x] 验证必需路径和数值范围。
- [x] 不在 `config.cfg` 中存放密钥。

## 10.2 必需的配置节

实现：

```text
[platform]
[auth]
[sandbox]
[storage]
[opencode]
[model_gateway]
[metrics]
[performance]
```

### Verification gate

- [x] 单元测试覆盖正常值、覆盖值和无效值。
- [x] `python -m app.main --check-config` 输出脱敏后的最终配置。

---

# 11. 实现 SQLite 注册表

## 11.1 架构

- [x] 创建 `agents`、`sandboxes`、`sessions` 表。
- [x] 启用 WAL 模式。
- [x] 强制执行唯一的 `(agent_id, username)` 沙箱键。

## 11.2 必需方法

```text
get_sandbox(agent_id, username)
upsert_sandbox(...)
mark_sandbox_status(...)
record_session(session_id, sandbox_id, agent_id, username, workspace_relpath)
get_session_route(session_id)
list_sessions_for_sandbox(...)
reconcile(...)
```

### 验证门槛

- [x] 为创建/更新/重启持久化编写单元测试。
- [x] 并发路由查找测试通过。

---

# 12. 实现工作区管理器

## 12.1 解析路径

对于 `(agent_id, username)`：

```text
workspace root = <workspace_root>/<agent_id>/<username>
state root     = <state_root>/<agent_id>/<username>/opencode
```

创建：

```text
shared/
sessions/
```

## 12.2 路径安全辅助函数

实现一个供**所有**上传/下载操作使用的规范辅助函数：

```python
resolve_user_path(agent_id, username, relative_path, session_id=None)
```

它必须：

- 拒绝绝对路径；
- 规范化路径；
- 保持在当前 Agent×User 根目录下；
- 防止通过符号链接逃逸；
- 仅在验证后创建父目录。

### 验证门槛

至少测试：

```text
normal/file.txt                   -> allow
../bob/file.txt                   -> reject
../../../../etc/passwd            -> reject
absolute /etc/passwd              -> reject
symlink that escapes workspace    -> reject
```

---

# 13. 使用 Docker SDK 实现沙箱管理器

## 13.1 沙箱标识

使用：

```text
sandbox_key = sha256(agent_id + "\0" + username) prefix
```

便于人工阅读的 Docker 标签仍是检查时的权威依据：

```text
cloud.agent_id
cloud.username
cloud.platform_instance
cloud.image_version
```

不要依赖可逆/base64 容器名称作为访问控制机制。

## 13.2 获取算法

实现：

```text
acquire(agent_id, username)
  -> per-key async lock
  -> registry lookup
  -> inspect container
  -> if healthy running: reuse
  -> if stopped: start + health
  -> if missing/broken: create + start + health
  -> persist target
  -> return sandbox endpoint
```

逐键锁十分重要，可防止同时到达的首次请求创建重复容器。

## 13.3 容器设置

- [x] 固定镜像版本；
- [x] rootfs 只读；
- [x] `/tmp` 使用 tmpfs；
- [x] 工作区以 RW 挂载；
- [x] 状态目录以 RW 挂载；
- [x] Agent 配置以 RO 挂载；
- [x] CPU/内存/PID 限制；
- [x] 不提供 Docker socket；
- [x] 不使用 privileged 模式；
- [x] 将 OpenCode 4096 暴露到随机的 `127.0.0.1` 主机端口；
- [x] 添加本地拓扑所需的主机/模型网关路由；
- [x] 启动环境禁用 OpenCode 动态更新/下载行为。

## 13.4 就绪状态

启动后：

```text
GET http://127.0.0.1:<host_port>/global/health
```

要求：

```text
healthy = true
version = config expected_version
```

### 验证门槛

- [x] 首次 `acquire(agent-code, alice)` 只创建一个容器。
- [x] 五个并发的 `acquire(agent-code, alice)` 调用仍然只创建一个容器。
- [x] `acquire(agent-code, bob)` 创建单独的容器。
- [x] `acquire(agent-data, alice)` 创建单独的容器。
- [x] Alice 沙箱无法通过其挂载看到 Bob 的主机工作区。

---

# 14. 实现网关原生路径代理

## 14.1 使用 FastAPI + HTTPX

- [x] 构建一个可转发未知 OpenCode 原生路径的通用代理路由。
- [x] 不要手动实现所有 OpenCode 端点逻辑。
- [x] `/cloud/files/*` 等显式云端路由优先于捕获全部路径的原生代理。

## 14.2 云端路由元数据

对于带 JSON 正文的写入请求：

```json
{
  "_cloud": {
    "agent_id": "agent-code",
    "username": "alice"
  }
}
```

对于 GET/DELETE/SSE：

```text
X-Cloud-Agent-ID
X-Cloud-Username
```

- [x] 转发前移除 `_cloud`。
- [x] 保留原生 `agent`、`model`、`parts` 等字段。

## 14.3 会话路由持久化

成功执行 `POST /session` 时：

- [x] 解析返回的原生会话 ID；
- [x] 保存会话 -> 沙箱映射。

对于后续 `/session/:id/...` 调用：

- [x] 优先通过会话映射解析；
- [x] 如果提供了显式路由元数据，则进行比较；
- [x] 拒绝不匹配的请求。

## 14.4 响应透明性

- [x] 状态码不变；
- [x] JSON/正文不变；
- [x] 转发相关响应头；
- [x] 仅对云端层故障使用云端错误。

### 验证门槛

黄金测试：

```text
POST /session
GET /session
GET /session/:id
POST /session/:id/message
GET /session/:id/message
POST /session/:id/abort
GET /file?path=.
GET /mcp
GET /global/health
```

比较直连沙箱的响应与经过网关的响应。

> OpenCode 1.18.29 实测：`GET /file` 缺少必需的 `path` 查询参数时返回 400；黄金调用使用 `path=.`。缺少 `parts` 的消息正文 `{}` 在第 24 阶段复验返回原生 400；无效消息用例校验错误透明透传，成功模型消息由第 19/24 阶段完整模型链路验证。

---

# 15. 正确实现 SSE 代理

## 15.1 必需路由

- [x] `/event`
- [x] `/global/event`

## 15.2 流式传输要求

- [x] 使用 `httpx.AsyncClient.stream` 或等效方式；
- [x] 按收到的顺序转发数据块；
- [x] 不要缓冲整个响应；
- [x] 保留 `text/event-stream`；
- [x] 将断开连接/取消传播至上游；
- [x] 暴露活跃 SSE gauge。

### 验证门槛

- [x] 将两个 SSE 客户端连接到 Alice 沙箱，并将两个连接到 Bob 沙箱。
- [x] 确认每个客户端仅接收所路由沙箱的事件。
- [x] 终止一个客户端，并确认网关释放上游流。
- [x] 内存不会因缓冲而随流的持续时间增长。

---

# 16. 添加文件上传/下载

## 16.1 上传

实现：

```text
POST /cloud/files/upload
```

- [x] multipart 流式传输；
- [x] 从配置读取最大请求大小；
- [x] 可选的 `session_id` 目标；
- [x] 写入时计算哈希；
- [x] 临时文件 + 原子重命名。

## 16.2 下载

实现：

```text
GET /cloud/files/download
```

- [x] 流式文件响应；
- [x] 安全的 content-disposition；
- [x] 通过共享工作区管理器辅助函数验证路径。

## 16.3 列表

实现最小功能：

```text
GET /cloud/files/list
```

### 验证门槛

- [x] 将 XLSX 上传到 Alice/agent-data/session-X。
- [x] Alice 沙箱内的 OpenCode/Python 可在返回的 `/workspace/...` 路径读取该文件。
- [x] 下载校验和等于上传校验和。
- [x] Bob 无法通过云端文件 API 将请求路由到 Alice 的工作区路径。
- [x] 路径遍历/符号链接测试安全失败。

---

# 17. 创建两个示例 Agent

## 17.1 `agent-code`

用途：

```text
repository analysis / code editing / shell / git
```

- [x] Agent 配置指向模型网关。
- [x] 允许的逻辑模型：

```text
coding-fast
coding-quality
```

- [x] 仅包含本地平台钩子/插件。

## 17.2 `agent-data`

用途：

```text
Excel/PPT/data analysis and visualization
```

- [x] 使用相同的基础运行时镜像。
- [x] Agent 专用指令/技能侧重 Python 数据栈。
- [x] 允许的逻辑模型：

```text
data-fast
data-quality
```

可按需复用物理模型后端；不同 Agent 策略仍可使用不同的逻辑名称。

### 验证门槛

- [x] `agent-code × alice` 正常工作。
- [x] `agent-data × alice` 在不同的沙箱中正常工作。
- [x] 除非某个 Agent 确实需要不同的运行时镜像，否则两者使用相同的基础镜像 ID。

---

# 18. 部署 LiteLLM 模型网关

实测修正：本机宿主端口使用 4001，容器内端口仍为 4000。只发布到 loopback 会导致沙箱访问 host gateway 失败，因此部署脚本同时发布到 Docker bridge 地址。日常存活探针使用 `/health/liveliness`，避免 `/health` 发起模型调用；指标端点可能重定向到 `/metrics/`。本阶段使用真实 LiteLLM 和本地可控 OpenAI 兼容后端验证传输、路由、故障和指标；不据此认定真实模型能力或最终外部模型验收通过。

验证 LiteLLM 之前，不要实现自定义 Python LLM 均衡器。

## 18.1 创建配置

创建包含逻辑模型组的 `config/litellm_config.yaml`。

概念示例：

```text
coding-fast
  -> deployment fast-1
  -> deployment fast-2

coding-quality
  -> deployment quality-1
  -> deployment quality-2
```

根据需要为数据 Agent 重复设置别名，或复用共享逻辑名称。

## 18.2 路由

- [x] 如果存在等价部署且目标是平衡并发，则首先使用 `least-busy`。
- [x] 配置重试和冷却。
- [x] 除非明确配置，否则不要在差异重大的模型类别之间静默回退。

## 18.3 Prometheus

- [x] 启用 LiteLLM Prometheus 回调/指标。
- [x] 验证 `/metrics` 包含请求延迟和流式 TTFT 指标。

### 验证门槛

- [x] 通过 LiteLLM 直接发送兼容 OpenAI 的请求成功。
- [x] 流式请求正常工作。
- [x] 出现 TTFT 指标。
- [x] 存在重复测试部署时，路由依据所配置策略分配并发流量。
- [x] 禁用一个部署会触发冷却/故障转移，而不是导致平台故障。

---

# 19. 将 OpenCode 指向模型网关

OpenCode 支持可配置的提供商 `baseURL`。

## 19.1 配置 Agent 提供商

- [x] 添加自定义/兼容 OpenAI 的提供商 ID，例如：

```text
cloud-model-gateway
```

- [x] 将其 `baseURL` 设置为模型网关内部 URL。
- [x] 仅定义获准的逻辑模型 ID。

## 19.2 验证原生模型正文

通过云端网关发送：

```json
{
  "model": {
    "providerID": "cloud-model-gateway",
    "modelID": "coding-fast"
  }
}
```

### 验证门槛

追踪必须显示：

```text
Client
-> Cloud API Gateway
-> correct Agent×User OpenCode sandbox
-> LiteLLM
-> chosen physical deployment
```

除健康/配置方面的考虑外，控制器代码不应需要知道 LiteLLM 使用的提供商 API 密钥。

---

# 20. 添加平台 Prometheus 指标

在 Python 控制器中使用 `prometheus-client`。

## 20.1 最小指标集

实现：

```text
HTTP request count/error/latency
SSE active count
sandbox active/starting count
sandbox create/start/ready latency
sandbox reuse count
sandbox failures
model gateway health status
workspace upload/download bytes
```

不要将用户名/会话 ID 用作 Prometheus 标签。

## 20.2 `/metrics`

- [x] 暴露控制器 `/metrics`。
- [x] 配置 Prometheus 抓取控制器和 LiteLLM。

### 验证门槛

- [x] 一次普通请求、一次上传和一次沙箱创建后，指标得到更新。
- [x] 不存在无界的高基数标签。

---

# 21. 添加健康监控

实现说明：`health_failure_threshold` 默认 3，可通过配置或环境覆盖。普通请求与 SSE 持有使用计数，连接结束才释放；后台原生异步会话通过 `/session/status` 阻止误回收。健康检查不重置空闲时钟，活动请求才更新时间。最终生命周期在空闲时停止并删除容器，但保留其工作区、状态和会话路由；下一次 acquire 重新创建并验证版本。正式启动入口为 `python -m app.main`，负责组合路由、指标和生命周期循环。

## 21.1 控制器端点

实现：

```text
GET /cloud/health
GET /cloud/health/ready
```

就绪检查：

- [x] SQLite；
- [x] Docker 守护进程；
- [x] 所需基础镜像存在；
- [x] 工作区根目录可写；
- [x] 模型网关健康状态。

## 21.2 沙箱健康循环

- [x] 使用 `/global/health` 定期探测活跃沙箱。
- [x] 连续失败达到可配置次数后标记为不健康。
- [x] 不要因一次暂时性探测失败就立即销毁沙箱。

## 21.3 空闲生命周期

- [x] 在原生请求/SSE 活动时更新 `last_active_at`。
- [x] 达到配置的超时后停止并删除空闲沙箱。
- [x] 保持工作区/状态持久化。
- [x] 下次请求时重新创建并进行健康检查。

### 验证门槛

- [x] 空闲沙箱停止并删除容器。
- [x] 下次请求会重新创建容器，且原工作区仍然存在。
- [x] 重建后重新验证 OpenCode 健康状态/版本。

---

# 22. 仅在指标正确后添加可选的 Grafana

- [x] 创建一个包含以下内容的最小仪表板：

```text
active sandboxes
sandbox cold-start p50/p95
SSE active connections
Gateway p50/p95 latency
Gateway error rate
LiteLLM TTFT p50/p95
model API latency p50/p95
model failures by logical model/deployment
host CPU/memory/disk
```

- [x] 核心负载测试通过前，不要在 UI 润色上花费时间。

---

# 23. 实现未来认证占位接口，但不启用认证

实现说明：`auth.token_endpoint_enabled` 控制占位端点是否可见；可见时返回 HTTP 501 / `AUTH_DISABLED`，隐藏时返回 404。占位路径限定在 `/cloud/auth/` 下，不能覆盖原生路由。`auth.enabled` 继续保持 false；认证适配器实现之前，误设为 true 会拒绝正式启动，不会静默跳过认证。

## 23.1 配置

```ini
[auth]
enabled = false
```

## 23.2 预留请求头

```text
Authorization: Bearer <jwt>
```

## 23.3 预留端点

```text
POST /cloud/auth/token
```

MVP 行为：

- [x] 端点根据配置返回 `501/auth disabled` 或被隐藏；
- [x] 网关不要求 JWT。

未来行为契约：

```text
existing user cookie
-> /cloud/auth/token
-> short-lived JWT
-> Authorization header
```

### 验证关卡

- [x] 启用/禁用占位功能不会改变任何 OpenCode 原生路径。

---

# 24. 上游 OpenCode 契约测试

每个发布版本都必须针对固定镜像执行测试。

## 24.1 冻结规范

- [x] 启动候选运行时镜像。
- [x] 将上游 `/doc` 构件保存到：

```text
docs/upstream/opencode-<version>-openapi.*
```

## 24.2 黄金 API 测试

测试直接访问和代理访问：

```text
/global/health
/session create/list/get/delete
/session/:id/message
/session/:id/abort
/event SSE
/file and /file/content
/mcp
/agent
/config/providers
```

## 24.3 云端元数据剥离

- [x] 证明 OpenCode 绝不会收到 `_cloud` 字段。

### 验证关卡

- [x] 任何意外的上游路由/模式变更都会阻止版本升级，直至完成审查。

---

# 25. 多用户隔离功能测试

创建：

```text
agent-code × alice
agent-code × bob
agent-data × alice
```

放置标记文件：

```text
Alice code workspace: ALICE_CODE_SECRET.txt
Bob code workspace:   BOB_CODE_SECRET.txt
Alice data workspace: ALICE_DATA_SECRET.txt
```

测试：

- [x] Alice 的代码沙箱只能看到 Alice 的代码挂载。
- [x] Bob 的代码沙箱只能看到 Bob 的代码挂载。
- [x] Alice 的数据沙箱只能看到 Alice 的数据挂载。
- [x] 检查容器挂载，确认没有挂载其他用户的工作区。
- [x] 猜测的宿主机路径在沙箱内不可访问。
- [x] 同属 Alice/agent-code 的会话可以看到彼此的 `/workspace/sessions/*`；将此记录为 V1 的预期行为。

---

# 26. 构建负载测试客户端

使用 Python asyncio + HTTPX。

创建：

```text
tests/load/run_load.py
```

为每个请求记录：

```text
request_id
agent_id
username
session_id
logical_model
request_start
sandbox_acquired_at
first_sse/model token observed
ttft_ms
completion_end
total_latency_ms
status
error
```

不要只依赖客户端 TTFT。应与 LiteLLM TTFT 指标比较。

---

# 27. 建立模型直连基线

验证结果：四个逻辑路由各 20 次真实流式请求全部成功，TTFT 指标增量为 80。结果及逐请求 JSON/CSV 已保存至 `artifacts/perf`。两个供应商分别由两个逻辑路由共享，重复部署槽位不构成独立副本。

在测试 OpenCode/平台开销之前：

针对两种逻辑模型分别执行：

- [x] 直接通过 LiteLLM 重复进行流式调用；
- [x] 收集 p50/p95 TTFT；
- [x] 收集 p50/p95 总延迟；
- [x] 记录到 `artifacts/perf/direct-model-baseline.json`。

此基线会计入提供商的波动。

---

# 28. 建立 OpenCode 沙箱直连基线

对于一个已经运行的沙箱：

- [x] 绕过云端网关；
- [x] 通过其本地发布端口直接调用 OpenCode 原生 API；
- [x] 测量会话创建、消息 TTFT 和完成延迟；
- [x] 保存到 `artifacts/perf/direct-opencode-baseline.json`。

---

# 29. 最终 2 Agent / 2 模型 / 4 并发测试

最终验收的解释：

```text
Each Agent receives 4 concurrent model requests:
- 2 using its fast logical model
- 2 using its quality logical model

Run both Agents at the same time:
2 Agents × 4 = 8 concurrent requests total.
```

至少使用两个不同的用户名，以测试 Agent×User 沙箱路由。

示例矩阵：

```text
agent-code:
  alice / coding-fast
  alice / coding-quality
  bob   / coding-fast
  bob   / coding-quality

agent-data:
  alice / data-fast
  alice / data-quality
  bob   / data-fast
  bob   / data-quality
```

## 29.1 热启动测试

- [x] 预先获取所有必需的沙箱。
- [x] 并发运行 8 个请求。
- [x] 重复足够多轮，以计算 p50/p95。

## 29.2 冷启动测试

- [x] 停止/移除测试沙箱，同时将镜像保留在本地。
- [x] 从不存在/已停止状态发起突发请求。
- [x] 分别测量沙箱就绪时间和模型 TTFT。

## 29.3 初始门槛

这些是平台开发门槛，并非对提供商绝对速度的声明：

```text
Gateway-induced 5xx during 8-way burst: 0
Cross-user routing failures: 0
Native path proxy overhead p95: <= 100 ms excluding model/sandbox time
Running-sandbox acquire p95: <= 500 ms
Cold container -> OpenCode healthy p95: <= 5 s on the reference machine
Model-Gateway TTFT overhead p95 vs direct backend baseline: <= 300 ms
```

对于绝对 TTFT：

```text
Report it, but compare it to the direct-model baseline.
```

一个实用的验收公式是：

```text
full_path_ttft_p95
<= direct_model_ttft_p95
 + measured OpenCode overhead
 + configured gateway overhead budget
```

如果平台增加的开销仍在预算内，不要仅仅因为外部提供商某天速度较慢就判定平台失败。

### 验证关卡

- [x] 保存完整的 JSON/CSV 报告。
- [x] 保存 Prometheus 快照/查询结果。
- [x] MainAgent 编写一页性能结论。

---

# 30. 针对有限内存/存储的资源压力测试

由于目标宿主机的内存/存储有限，应运行受控扩展测试。

- [x] 测量一个空闲 Agent 沙箱的 RSS/内存用量。
- [x] 测量一个活跃的 OpenCode 请求。
- [x] 在适用时，测量启用了 LSP/MCP 的 Agent。
- [x] 仅在机器容量允许时，依次创建 10、20、50 个轻量级空闲沙箱。
- [x] 记录 Docker 镜像大小和每个用户的持久化状态增长量。
- [x] 验证基础镜像层会被共享；不要以 `N × image size` 推断磁盘成本。

在宿主机换页/资源争用使结果失去意义之前停止测试。

输出：

```text
artifacts/perf/resource-capacity.md
```

为参考服务器提供建议的生产并发限制。

---

# 31. 故障与恢复测试

## 31.1 终止沙箱

- [x] 在空闲状态下强制停止一个 Agent×User 容器。
- [x] 下一个请求应重启/重新创建该容器。

## 31.2 控制器重启

- [x] 保持沙箱运行。
- [x] 重启控制器。
- [x] 协调 SQLite 与 Docker 标签。
- [x] 如果沙箱/状态仍然有效，现有会话路由应能解析。

## 31.3 模型部署故障

- [x] 禁用一个 LiteLLM 物理部署。
- [x] 验证路由器的冷却/故障转移行为。

## 31.4 SSE 客户端断开连接

- [x] 在数据流传输中途断开客户端连接。
- [x] 验证上游资源被释放。

## 31.5 磁盘压力

- [x] 使用配置的小型测试配额模拟工作区配额耗尽。
- [x] 上传返回清晰的云端错误；现有工作区保持完整。

---

# 32. 日志记录

在控制器中实现结构化 JSON 日志。

字段：

```text
timestamp
level
request_id
component
action
agent_id
username_hash or safe username where appropriate
sandbox_id
container_id prefix
session_id only in logs, not metrics
status_code
duration_ms
error_code
```

- [x] 不得记录模型 API 密钥/JWT/提供商密钥。
- [x] 不得记录上传的二进制内容。

### 验证关卡

- [x] 可以使用请求关联元数据，沿网关 -> 沙箱 -> 模型网关追踪一个用户请求。

---

# 33. 冻结依赖项

最终打包前：

- [x] 使用哈希/锁文件冻结 Python 依赖项；
- [x] 固定 LiteLLM 版本；
- [x] 固定 OpenCode 版本；
- [x] 固定 Node 补丁版本；
- [x] 在可行时固定基础镜像摘要；
- [x] 记录验收测试所用的 Docker Engine/运行时兼容性。

不得仅以 `latest` 标签作为发布包的可复现机制。

---

# 34. 构建生产镜像

至少构建/冻结：

```text
cloud-agent-runtime:<release>
cloud-agent-controller:<release>
model-gateway:<release>
```

如果目标是在目标宿主机上实现零拉取，则完整离线发布包可以包含监控镜像。

### 验证关卡

- [x] 扫描镜像历史，检查是否意外包含密钥。
- [x] 从干净状态启动所有生产标签镜像。
- [x] 再次运行冒烟测试。

---

# 35. 创建部署脚本

创建：

```text
deploy/doctor.sh
deploy/install.sh
deploy/start.sh
deploy/stop.sh
deploy/restart.sh
deploy/status.sh
deploy/logs.sh
deploy/uninstall.sh
```

## 35.1 `doctor.sh`

检查：

- [x] 是否为受支持的 Linux；
- [x] 架构是否与镜像包匹配；
- [x] Docker 是否可访问；
- [x] cgroup/运行时基础条件；
- [x] 所需端口是否空闲；
- [x] 最低磁盘空间；
- [x] 最低内存；
- [x] 配置解析是否成功；
- [x] 工作区根目录是否可写。

## 35.2 `install.sh`

- [x] 创建 `/srv/cloud-agent/...` 目录；
- [x] 加载打包的 Docker 镜像；
- [x] 安装/复制配置模板；
- [x] 未备份时，绝不覆盖现有的自定义 `config.cfg`；
- [x] 初始化 SQLite 模式；
- [x] 启动模型网关/控制器/监控；
- [x] 运行就绪检查。

### 验证关卡

在干净且兼容的 Linux/WSL 环境中运行，并验证从安装到服务健康的一条命令路径。

---

# 36. 构建便携式发布包

目标：

```text
cloud-agent-release-<version>/
├── VERSION
├── README.md
├── config/
├── deploy/
├── monitoring/
├── images/
│   ├── cloud-agent-runtime_<version>.tar.zst
│   ├── cloud-agent-controller_<version>.tar.zst
│   └── model-gateway_<version>.tar.zst
└── checksums.sha256
```

导出镜像：

```bash
docker save <image> | zstd -T0 -19 -o images/<image>.tar.zst
```

生成校验和：

```bash
sha256sum images/* > checksums.sha256
```

最后，将发布目录打包为 ZIP 以便传输。

### 验证关卡

- [x] 将发布 ZIP 复制到干净的 Linux 测试环境。
- [x] 解压。
- [x] 运行 `doctor.sh`。
- [x] 运行 `install.sh`。
- [x] 启动平台。
- [x] 不使用开发检出目录，运行最终冒烟测试和 8 路突发测试。

---

# 37. 最终验收清单

2026-09-08 最终验收通过：174 项单元测试，120/120 并发与 80/80 配对 TTFT 请求；最终 ZIP 干净安装真实八路请求 8/8 成功，重启/卸载/持久化/零 swap 检查通过。最终交付为 `artifacts/release/final/cloud-agent-release-0.1.0.zip`，完整证据及测量边界见 `artifacts/release/final-assessment.md` 和 `final-acceptance.json`。旧的顶层 ZIP 保留作历史候选，不能替代最终包。

只有以下各项全部满足时，MainAgent 才可宣布 V1 完成：

- [x] WSL 全新安装过程可复现。
- [x] Node/OpenCode/Python 版本已固定。
- [x] OpenCode 启动时无需动态更新/插件/LSP/模型目录下载。
- [x] Docker/runc Agent 运行时镜像具有确定性。
- [x] Agent 是逻辑定义。
- [x] 沙箱键为 `(agent_id, username)`。
- [x] 同一用户的会话复用同一个 OpenCode 服务器。
- [x] Bob 的工作区绝不会挂载到 Alice 的沙箱。
- [x] 云端网关保留 OpenCode 原生路径。
- [x] `_cloud` 路由元数据在转发前已被剥离。
- [x] GET/DELETE/SSE 无需请求体即可路由。
- [x] `/event` 和 `/global/event` 能正确进行流式传输。
- [x] 特定 Agent/用户/会话文件夹的上传/下载正常工作。
- [x] LiteLLM 模型网关能够路由已配置的逻辑模型。
- [x] 已收集 TTFT 和延迟指标。
- [x] 已测试模型故障/冷却路径。
- [x] 已记录沙箱冷/热启动时间。
- [x] 2 个 Agent × 4 个并发请求 = 共 8 个并发的最终突发测试通过。
- [x] 已测试控制器重启恢复。
- [x] `config.cfg` 控制重要运行时参数。
- [x] 身份认证保持禁用，但已预留 JWT 请求头/令牌端点契约。
- [x] 发布 ZIP 可在干净且兼容的 Linux 环境中安装。
- [x] 最终文档包含实际测得的性能值和参考机器规格。

---

# 38. 停止条件/升级处理规则

如果发生以下任何情况，MainAgent 必须停止推进并展开调查：

1. OpenCode 某项被认为是原生的功能实际需要源代码补丁。
2. `_cloud` 元数据泄漏到 OpenCode 中并破坏模式。
3. SSE 代理缓冲数据或丢失取消语义。
4. 某个 Agent 沙箱可以看到另一个用户的工作区挂载。
5. 新沙箱在启动时尝试下载必需的软件包。
6. OpenCode 确切版本在未显式提升版本号的情况下发生变化。
7. 并发情况下为同一个 `(agent_id, username)` 创建了重复容器。
8. 模型路由在没有显式回退策略的情况下更改了请求的逻辑模型。
9. 负载测试显示宿主机在达到目标并发量前发生换页/OOM。
10. 发布安装依赖开发者主目录中的隐藏文件。

对于每个阻塞问题，MainAgent 必须记录根本原因、最小修复方案、回归测试，以及是否需要修订架构决策。

---

# 39. 本 TODO 所依据的已验证上游事实（2026-09-06）

- OpenCode 建议在 Windows 开发中使用 WSL，并支持通过 npm 安装。
- OpenCode `serve` 公开 `/global/health`、`/doc`、会话/消息/文件/MCP 和 SSE API。
- OpenCode 记录了包括 `OPENCODE_DISABLE_AUTOUPDATE`、`OPENCODE_DISABLE_DEFAULT_PLUGINS`、`OPENCODE_DISABLE_LSP_DOWNLOAD` 和 `OPENCODE_DISABLE_MODELS_FETCH` 在内的开关。
- OpenCode npm 插件依赖项可能在启动时安装，因此为实现确定性的沙箱启动，应优先使用本地/预构建插件。
- OpenCode 自定义提供商支持 `baseURL` 和 OpenAI 兼容提供商。
- LiteLLM 可充当具备路由/回退和 Prometheus TTFT 指标的 OpenAI 兼容模型网关。
- 截至设计日期，Node.js 24 是 LTS 系列；发布时仍须固定并测试准确的补丁版本，而不能依赖浮动的 LTS 标签。

起草时使用的参考资料：

- https://opencode.ai/docs
- https://opencode.ai/docs/server/
- https://dev.opencode.ai/docs/cli/
- https://opencode.ai/docs/config
- https://opencode.ai/docs/providers/
- https://opencode.ai/docs/plugins/
- https://docs.litellm.ai/
- https://github.com/BerriAI/litellm-docs/blob/main/docs/proxy/prometheus.md
- https://nodejs.org/en/download
