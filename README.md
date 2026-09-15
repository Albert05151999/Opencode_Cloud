# OpenCode Cloud

OpenCode 的多服务平台与独立本地管理 Web。服务器提供模型、Agent、资源、会话、文件和沙箱；本地 Web 用于配置与使用。

## 开始使用

1. 根目录 `.env` 配置供应商 Key；没有 Key 就安装空平台。
2. 可选 `PRESET_AGENTS=code:glm,data:minimax`，安装时创建并发布两个 Agent。留空不创建预设 Agent。
3. 在 Linux 或 WSL 仓库根目录构建服务器：
   `python3 build_image/build.py bundle`。
4. 上传 `artifacts/releases/release-0.3.2.tar.gz`，服务器解压后执行 `sh install.sh`。
5. Windows PowerShell 在源码根目录执行：
   `python admin_web/build.py --version 0.3.2`，
   再执行 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\admin_web\scripts\start.ps1`。

本地打开 `http://127.0.0.1:18765`，连接 `http://服务器IP:18080`，凭据使用服务器发布目录 `.env` 的 `ADMIN_TOKEN`。

- [完整部署与故障处理](docs/deployment.md)
- [模型、账户池和 Agent 配置](docs/model-configuration.md)
- [导入导出与配置包恢复](docs/import-export.md)

构建自动读取根 `.env`，私有配置随离线包交付，不进入镜像层。`server.cfg` 保存运维连接信息，不打包。已有平台通过管理页面修改配置，重复安装不覆盖用户修改。

## 代码目录

| 目录 | 职责 |
| --- | --- |
| api_gateway | 统一认证和 API 入口 |
| catalog_service | 模型、资源、Agent 配置与版本 |
| model_gateway | LiteLLM 模型映射与账户池 |
| sandbox_manager / agent_runtime | 沙箱生命周期与 OpenCode 运行环境 |
| file_service / operations / observability | 文件、发布任务、日志和观测 |
| admin_web | 独立本地管理 Web |
| config / build_image / test | 配置、构建和测试 |

生成的发布包、运行数据和日志位于 artifacts、data、log。服务模块分别使用独立依赖锁与镜像；agent_runtime 按会话需要启动。

## 开发验证

Linux / WSL 开发环境安装项目测试依赖后执行 `python3 -m pytest test`。涉及 shell、Unix 信号和 Docker 的测试在 Linux 运行；Windows 本地 Web 使用 PowerShell 启动并做浏览器验证。发布包版本读取根 VERSION，镜像标签读取各模块版本。
