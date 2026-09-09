# 从全新 clone 构建与部署

源码构建不需要旧发布 ZIP、WSL 备份、`deploy/.env` 或历史验收报告。镜像输入由 `versions.env`、Dockerfile 和依赖锁文件固定。构建需要联网，生成的服务端包包含离线镜像；Web 包包含编译页面，用户使用时无需 Node.js。

## 构建环境

使用 Linux x86_64 或 Windows 的 Ubuntu 24.04 WSL。在源码根目录的 WSL 终端执行，Docker 必须是该 Linux 环境可访问的本地引擎；验证会启动临时容器并使用宿主机目录挂载。需要 Python 3.12、venv、Docker、zstd、curl、Node.js 24 和 npm。不要在生产服务器执行构建验证。

Ubuntu 可先安装基础工具（Docker 按当前环境单独安装）：

```bash
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv zstd curl xz-utils
docker info
node --version
npm --version
```

未安装 Node.js 时，可使用项目中的 `sudo bash scripts/install-node.sh`，它按 `versions.env` 安装固定版本。

## 一键构建

```bash
bash scripts/build-from-source.sh
```

脚本创建 `.venv-build`、安装构建依赖、执行 `npm ci` 和前端构建、运行单元测试、构建与验证 runtime/controller/模型网关镜像，并拉取固定摘要的监控镜像，最后直接从源码生成两份 ZIP。

输出在 `artifacts/release/web-v<VERSION>/`，包含服务器包、本地 Web 包和 `package-verification.json`。如果输出目录已经存在，使用新的输出目录，避免覆盖正在部署的包：

```bash
bash scripts/build-from-source.sh --output-dir artifacts/release/source-build
```

ZIP 内容、时间戳可能使重新构建后的 SHA256 与旧交付物不同。部署时以本次 `package-verification.json` 为准，不套用旧发布包的固定哈希。

## 部署与使用

1. 在项目根目录的 PowerShell 中执行 `Copy-Item .\deploy\.env.example .\deploy\.env`（仅首次；已有文件不要覆盖），填写自己的模型凭据。真实 `.env` 被 Git 忽略，也不会进入包。
2. 按根目录 [部署指南](../部署指南.md) 第 3～4 节准备 `.env` 并上传本次服务器 ZIP；校验值直接从同批次 `package-verification.json` 读取。
3. 按指南第 5 节首次安装，解压并执行 `deploy/install.sh`；已经部署的服务器直接跳到第 6 节配置本地 Web。该指南不包含升级流程。
4. 本地解压本次 Web ZIP，运行 `start-web.ps1`，在 localhost 管理页填写服务器 URL 和管理员令牌，再测试连接并聊天。Web 首次启动需要 Python 3.11+ 和联网安装依赖。

全新 clone 的 `web/dist` 尚不存在；必须先构建，或使用已构建的 Web ZIP。旧版升级回归脚本所需的历史包属于可选测试夹具，不是构建或正常部署依赖。
