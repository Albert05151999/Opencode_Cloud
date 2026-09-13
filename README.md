# OpenCode Cloud

OpenCode 的多服务部署与本地管理客户端。服务器通过统一 API 提供 Agent、模型、资源、文件、沙箱、发布任务和日志查询；`admin_web` 独立打包，服务器构建和运行不需要它。

## 目录与职责

| 目录 | 内容 |
| --- | --- |
| `api_gateway` | 公开 API、入口认证、流式转发 |
| `catalog_service` | 模型、Agent、资源目录与版本编译 |
| `sandbox_manager` | Docker 沙箱生命周期、会话注册表 |
| `file_service` | 工作区分配、上传下载、文件权限 |
| `model_gateway` | LiteLLM 路由、模型配置激活、推理接口 |
| `operations` | 发布、恢复、删除、压测任务及持久状态 |
| `observability` | 模块日志与 trace 查询 |
| `agent_runtime` | OpenCode、Node.js、Python 沙箱镜像资源 |
| `admin_web` | 前端与本机回环地址上的 Python 伴随服务 |
| `config` / `build_image` / `test` | 部署配置、构建安装工具、按模块组织的验证 |
| `contracts` / `shared_libs` | 版本化接口与固定版本共享库 |
| `data` / `log` / `artifacts` | 持久数据、运行日志、生成产物 |

每个服务器模块通过自己的 `module.yaml`、依赖锁和 Dockerfile 构建；构建上下文只包含显式模块输入与固定版本共享库。发布包包含多个独立镜像，`agent_runtime` 由沙箱管理器按需创建。

## 构建与运行

在仓库根目录执行，构建目标为 Linux amd64：

```bash
# 无需 Docker：生成配置、隔离构建上下文和部署脚本
python3 build_image/build.py bundle --profile production --mode ip --prepare-only

# 需要可用 Docker：单模块镜像或完整服务器离线包
python3 build_image/build.py module operations --profile production
python3 build_image/build.py bundle --profile production --mode ip

# 独立客户端，构建时需要 Node/npm
python3 admin_web/build.py --version 0.3.0

# 收集服务器与客户端部署 shell 脚本
python3 build_image/tools/export_scripts.py
```

服务器归档：`artifacts/releases/release-0.3.0.tar.gz`。客户端归档：`artifacts/admin_web/0.3.0/admin_web-0.3.0.tar.gz`。

`artifacts/scripts/server/` 和 `artifacts/scripts/admin_web/` 是脚本集中输出目录。服务器脚本必须与完整离线包的 `compose.json`、配置和镜像归档一起使用；单独复制脚本不能完成安装。客户端集中导出的脚本需要设置 `ADMIN_WEB_ROOT`，指向解压后包含 `admin_web/` 的目录。

默认 IP 入口为 `http://服务器IP:18080`，不构建或启动 Nginx。域名模式可选 Nginx，并需要自行准备 DNS 和证书。安装、配置、初始化发布、升级及旧数据迁移见 [部署指南](docs/deployment.md)。

`production` 是交付默认配置。仓库中的 `acceptance` / `acceptance_domain` 只用于受限验收虚拟机，将默认 Agent 调低到 1 CPU / 1 GiB，并把冷启动等待放宽到 120 秒；不要把这些参数当作生产容量建议。production 默认 Agent 资源为 2 CPU / 2 GiB，普通沙箱启动等待为 15 秒，应按真实并发与模型启动时间评估后再覆盖。

配置种子可通过显式命令预览和导入，服务启动不会自动覆盖 catalog：

```bash
python3 -m config.tooling seed-import models.example.json
# 修改配置与凭据后，按部署指南使用 --apply、--revision 和明确的服务地址
```

## 验证与当前边界

```bash
# 需要 uv；每个服务使用全新独立 Python 3.12 环境安装依赖并导入
python3 build_image/tools/verify_dependencies.py

# 开发验证环境（独立服务镜像仍分别使用自己的锁文件）
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e '.[test]'
.venv/bin/python -m pytest test

# 完整离线服务器包及独立 Admin 客户端
python3 build_image/build.py bundle --profile production --mode ip
python3 admin_web/build.py --version 0.3.0
```

本轮已实际构建 8 个 Linux amd64 镜像，并在全新的 Ubuntu x86_64 主机从无源码离线包安装。IP 入口、带测试证书的 HTTPS 入口、模型和 Agent 发布、真实 OpenCode 会话、SSE、工具调用、文件、压测、沙箱生命周期、日志与跨模块 trace 均通过；模型端使用可控的 OpenAI 兼容协议服务验证完整网络链路。独立打包的 Admin 客户端也已从归档安装并通过真实局域网浏览器检查。

后续已在重新安装的 Ubuntu 上完成真实供应商部署链验收：MiniMax-M3 全流程包含单用户压测及清理，GLM-5.3 基础流程刻意不重复压测；两者均通过真实 bash 执行 Python 得到 5050、SSE、文件往返、沙箱停止/启动和 trace。独立打包 Admin 的局域网浏览器、原会话整机重启恢复后再次工具调用、严格验证 TLS 的 Nginx 入口在原会话新增工具调用得到 42 及 trace 均通过。模型导入 CLI 与实际沙箱安全属性也已验证。证据位于 `artifacts/verification/real-system-{minimax,glm,restart,domain,security,seed-import}.json` 和 `artifacts/verification/admin_web/real-provider-lan-smoke.json`。

本轮复用已验证的生产镜像，临时验收覆盖为 1 CPU / 1 GiB、启动等待 120 秒；未重新构建镜像或重跑全部单元测试。此前 Linux 全量回归为 403 项通过，主环境跳过的 1 项 LiteLLM 测试在独立环境补测通过；此前单模块回滚、Nginx 日志轮转与优雅退出的证据继续保留。本轮 Ubuntu 虚拟机、临时数据和虚拟机工具已销毁，测试端口已关闭，清理证据见 `artifacts/verification/real-system-cleanup.json`。公开模板仍不含密钥，部署者须提供自己的模型配置。

测试代码的整理集中在公共 fixture、HTTP transport、服务配置和辅助断言的复用，同时保留参数 case 与独立失败路径。新增的 Linux、协议和浏览器真实验收脚本扩大了测试范围，因此不能仅用整个 `test/` 目录总行数判断去重效果。

性能验收单独记录冷启动、热请求和并发延迟，不以单用户功能/推理成功作为达标依据。复测脚本见 `test/performance/benchmark.py`；阶段调用链与测量口径见[部署指南](docs/deployment.md)。
