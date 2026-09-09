# 构建思路与自动化验证约定

## 原则

构建负责下载和安装，运行期只启动服务。所有依赖候选版本只在开发或构建阶段发现；通过验证后写入版本文件。升级版本必须重新执行对应验证，不能在请求路径使用 `latest`、拉取镜像或安装依赖。

`versions.env` 固定 Node/OpenCode/Python 版本及基础、模型网关、监控镜像摘要。`requirements-controller.lock` 和 `runtime/requirements.lock` 固定生产 Python 全传递依赖和哈希，`runtime/package-lock.json` 固定 OpenCode npm 依赖图。更新及验证方式见 `docs/dependency-freeze.md`。

## 已实现的构建和验收入口

以下命令均在 Ubuntu 24.04 x86_64 上运行，工作目录为项目根目录。需要系统写权限的安装脚本使用 root，验证脚本使用普通用户。

| 环节 | 安装入口 | 独立验收入口 | 证据 |
| --- | --- | --- | --- |
| 系统工具 | `bash scripts/setup-ubuntu.sh` | 工具版本检查、`dpkg --audit`、`apt-get check` | `artifacts/env/ubuntu-baseline.txt` |
| Node | `bash scripts/install-node.sh` | `bash scripts/verify-node.sh` | `artifacts/env/node-baseline.txt` |
| OpenCode | `bash scripts/install-opencode.sh` | `python3 scripts/verify-opencode.py` | 健康结果、原生 OpenAPI JSON |
| 确定性启动 | `runtime/entrypoint.sh` | `python3 scripts/verify-opencode.py --stabilized` 和 `--config-check` | 网络 trace、出站连接检查、实际生效配置 |
| Python 分析依赖 | `bash scripts/setup-python-runtime.sh` | 虚拟环境 Python 执行 `scripts/verify-python-runtime.py` | XLSX/PPTX/PNG/YAML 和 JSON 报告 |
| 运行时镜像 | `docker build`（由脚本调用） | `bash scripts/verify-runtime-image.sh` | `artifacts/runtime-image/report.json` |
| Agent×User 沙箱 | 无运行期拉取 | 以 root 执行 `python scripts/verify-sandbox.py` | `artifacts/sandbox/report.json` |
| 模型网关 | 固定 `versions.env` 中 LiteLLM tag/digest | `python scripts/verify-litellm.py` | `artifacts/litellm/report.json`、`metrics.prom` |
| 原生模型路由 | 复用同一运行时镜像 | `python scripts/verify-model-routing.py` | `artifacts/model-routing/report.json` |
| 健康/空闲回收 | 正式控制器入口组合模块 | `python scripts/verify-health.py` | `artifacts/health/report.json` |
| SSE 释放 | 无安装 | `python scripts/verify-sse.py` | `artifacts/sse/report.json`，连接数/使用计数均归零 |
| 上游规范冻结 | 按版本保存 `/doc` | `python scripts/verify-gateway.py` | `docs/upstream/`、`artifacts/gateway/report.json` |
| 负载客户端 | asyncio + HTTPX | `python scripts/verify-load-client.py` | `artifacts/perf/load-client-*`（本地可控模型冒烟） |
| 真实模型基线 | 先配置并启动 LiteLLM 的真实提供商 | `python scripts/verify-model-baseline.py --source-label <部署说明>` | `artifacts/perf/direct-model-baseline.json`、各模型 JSON/CSV 和前后指标快照 |

Python 虚拟环境路径通过 `CLOUD_AGENT_VENV` 指定。开发默认在当前用户的 `~/projects/cloud-agent/.venv`，镜像构建时可指定 `/opt/runtime/venv`。镜像不得依赖开发者主目录或 WSL 备份。

参考机器的构建代理位于 Windows/WSL mirrored loopback。聚合镜像验证在检测到 `HTTPS_PROXY=http://127.0.0.1:*` 时，为 `docker build` 添加 `--network host`，否则构建容器会把该地址解析为自身。构建网络与运行网络独立：Agent 使用 bridge，生产控制器和监控服务按部署配置使用 host 网络；CI/服务器可提供普通可路由代理或直接出网。

`scripts/verify-runtime-baseline.sh` 聚合上述运行时验证，任何一步失败即退出；该入口必须在依赖安装完成后运行。它不代表 Docker、隔离、模型或最终发布验收通过。

## 已实现的生产构建与发布入口

使用已安装控制器依赖的 Python 虚拟环境，在 Linux 项目根目录执行；Docker 构建、安装和验证须具备相应宿主机权限。

| 入口 | 行为与关卡 |
| --- | --- |
| `bash scripts/python-dependency-locks.sh verify` | 两个干净虚拟环境的哈希安装和依赖一致性检查 |
| `python scripts/verify-npm-lock.py` | 固定 npm 图安装、显式 OpenCode postinstall、精确版本检查 |
| `python scripts/build-release-images.py` | 串行构建运行时和控制器，冻结 LiteLLM 发布标签；运行时只读/重启/断网、控制器容器冒烟、模型故障冷却、镜像历史审计 |
| `python scripts/package-release.py --stage-only` | 按允许列表组装发布目录，导出五个镜像、固定两种 Docker 存储的内容身份并生成 SHA-256；排除并扫描实际密钥 |
| `python scripts/package-release.py` | 在以上步骤后生成 ZIP；压缩固定两线程，避免不受限内存压力 |
| `python scripts/verify-release-package.py artifacts/release/cloud-agent-release-0.1.0.zip` | 全新独立 daemon 仅接收 ZIP 和外部 key，执行解压、doctor、安装、真实八路模型突发、重启和卸载保留数据检查 |
| `python scripts/verify-v2-events.py` | v2 会话路由、持久事件流、响应头返回前断开及使用计数归零 |
| `python scripts/verify-stage29.py` | 当前源码指纹下重新运行单元、健康回收、160 次原生代理测量、120 次真实并发请求和四模型配对 TTFT |
| `python scripts/verify-stage37.py --zip <最终ZIP>` | 检查最终证据、源码指纹、镜像身份、ZIP 哈希及包内文档一致性，生成最终验收报告 |

ZIP 验证环境使用固定 DinD 镜像；Alpine 的 bash/Python/zstd/unzip 是该临时宿主机先决条件，安装完成后应用从包内镜像启动，不拉取应用镜像。临时 daemon 与 WSL 共享内核，报告明确此边界。生产主机仍需预装兼容 Docker Engine/Compose 与上述主机工具。

仅修改控制器且运行时输入未变时，可用 `SKIP_BUILD=1 python scripts/build-release-images.py` 复用已验收的运行时镜像；运行时冒烟和断网验证仍会执行。首次构建或运行时输入变更时不得设置此选项。BuildKit 的构建证明元数据可能改变镜像 ID，即使应用层相同，也不能将重复构建宣称为字节相同。

历史打包目录发现不属于当前镜像 ID 的旧归档时会拒绝继续。新候选包可指定 `--directory artifacts/release/final/cloud-agent-release-0.1.0`，保留旧失败证据；验证命令及 `verify-stage37.py --zip` 必须指向同一个最终 ZIP。性能验收期间不要并行加载或导出镜像。

当前构建步骤如下：

1. 校验版本文件与锁文件，拒绝缺失版本或浮动标签。
2. 构建 `runtime/Dockerfile`；镜像内复用相同的版本及依赖输入，不重复维护另一套版本。
3. 以普通用户、只读根文件系统、受限资源和临时专用 workspace/state/config 挂载启动候选镜像。
4. 在镜像内运行 Python 文件验收，在镜像外验证 OpenCode 精确版本、原生 API、启动网络、持久化重启和禁止写入路径。
5. 用独立测试租户执行路由、隔离、SSE 取消、模型路由和并发性能验证。真实模型测试需提供部署端点与密钥；模拟测试不得冒充真实模型性能。
6. 生产候选标签必须通过门禁后才能导出和打包；镜像身份记录在构建报告及发布清单中。任何重建导致 ID 变化，都需重新验收并同步配置，不能仅沿用同名标签。
7. 在干净 Linux 环境解压发布包，仅依赖包内文件完成安装、健康检查和最终并发验收。

每次运行保存版本、命令、退出码、测量值和失败原因；CI 保留失败日志。测试只清理本次创建并有明确标识的进程、容器和临时目录。任何失败均阻止后续构建阶段或发布，不能用“代码写完”代替门禁。

## 当前验证边界

最初的启动 trace 只覆盖健康请求。第 30 项进一步执行断网原生搜索、会话创建、配置和 MCP 查询，并观察 30 秒，确认全新默认项目初始化不产生 npm 缓存；第 32 项加入无外部依赖的本地日志插件后也已回归通过。用户主动创建 `.opencode` 项目配置仍可能触发 OpenCode 依赖安装，工具和模型请求本身也可产生网络流量。

第 29 项真实 120 请求性能关卡、第 30 项 20 个空闲沙箱容量与回收、第 31 项崩溃恢复和 SSE 取消、第 32 项真实日志关联均已通过。它们是对应版本的阶段证据；最终生产镜像和部署包仍须重新验收。`scripts/verify-sandbox.py` 只清理带本次验证实例标签的测试容器和临时目录。各阶段完成状态以 `docs/progress.json` 和主开发清单为准。
