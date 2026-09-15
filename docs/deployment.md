# 安装和使用

服务器运行在 Linux amd64，本地管理 Web 运行在你的电脑上。默认服务器入口为 `http://服务器IP:18080`，本地页面为 `http://127.0.0.1:18765`。

## 1. 准备配置

在仓库根目录复制 `.env.example` 为 `.env`，已有文件直接编辑。构建自动读取它。

```dotenv
MINIMAX_API_KEY=你的MiniMaxKey
ZAI_API_KEY=你的智普Key
PRESET_AGENTS=code:glm,data:minimax
```

这会预配置两个全局模型和两个 Agent：Code 使用 GLM，Data 使用 MiniMax。核对上游 URL 和模型名称与你购买的套餐一致。第二个账户填 `MINIMAX_API_KEY_2` 或 `ZAI_API_KEY_2`，加入同一模型账户池。

想在页面手动配置：将供应商 Key 和 `PRESET_AGENTS` 留空。平台仍可安装、登录，模型与 Agent 列表为空，页面提供两个示例。只有 Key、没有 `PRESET_AGENTS` 时，仅预配置模型。

已有配置包时使用 `BOOTSTRAP_BUNDLE=配置包路径`，加密包还需 `BOOTSTRAP_PASSWORD`；清空简单预设的供应商 Key 和 `PRESET_AGENTS`，避免冲突。见[导入导出](import-export.md)。

`ADMIN_TOKEN` 是本地 Web 连接凭据，留空由安装生成，非空保留。`SERVICE_TOKEN` 和 `MODEL_GATEWAY_TOKEN` 用于内部服务，不填入管理页面。`server.cfg` 只用于运维连接，不进入发布包。

## 2. 从代码构建

构建机器需要 Python 3、可用的 Docker Engine。首次构建需要联网下载锁定依赖。Windows 使用 WSL Ubuntu 构建 Linux 镜像，在 WSL 进入仓库：

```bash
cd /mnt/e/Project_Space/Opencode_Cloud
python3 build_image/build.py bundle
```

Linux 工作站在自己的仓库目录执行同一 Python 命令。成功生成 `artifacts/releases/release-0.3.2.tar.gz`，包含镜像、脚本和配置。

根 `.env` 的服务及模型字段进入私有包，凭据不进入 Docker 镜像层。传递完整归档即可。`--prepare-only` 只准备材料，不产生可安装包。

## 3. 在服务器安装

服务器需要 Linux amd64、Python 3，以及当前用户可使用的 Docker 和 Compose。先验证：

```bash
python3 --version
docker info >/dev/null
docker compose version
```

将归档上传到服务器家目录，在服务器执行：

```bash
cd ~
tar -xzf release-0.3.2.tar.gz
cd release-0.3.2
sh install.sh
./status.sh
curl -fsS http://127.0.0.1:18080/cloud/health
```

安装校验文件、补齐脚本权限和空缺令牌、检查端口、加载镜像并启动服务。有预配置时还会导入模型、发布模型网关、创建并发布 Agent；所有步骤完成才报告成功。`agent_runtime` 按会话需要创建，不要求它常驻出现在 Compose 列表中。

无预配置时会报告平台就绪、尚未配置模型，这是正常结果。重复安装保留已完成的初始化，不覆盖页面修改。中断后重试从记录阶段继续，无法确认的冲突会明确停止。已安装平台请通过页面修改模型，不要靠改 `.env` 后重装覆盖配置。

## 4. 已遇到问题的处理

### Permission denied

归档固定保存脚本权限，安装也会补齐。解压工具丢失权限时：

```bash
cd ~/release-0.3.2
chmod 755 ./*.sh
sh install.sh
```

归档里的 `./` 表示当前目录，不是另一个需要进入的部署目录。

### 18080 被占用

安装在加载镜像前检查冲突。服务器查明占用者：

```bash
sudo ss -ltnp '( sport = :18080 )'
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

停止确认不再使用的旧服务，或修改发布目录 `.env` 的 `API_PORT`，再运行 `sh install.sh`。本地 Web 的服务器地址也要使用新端口。

### 容器健康但 curl 连接失败

实际遇到过网关缺少宿主端口映射。`install.sh` 和 `start.sh` 会检查并尝试只重建网关一次。手动排查：

```bash
./compose.sh ps -a api_gateway
./compose.sh logs --tail=80 api_gateway
./compose.sh up -d --no-deps --force-recreate --wait api_gateway
curl -fsS http://127.0.0.1:18080/cloud/health
```

服务器本机可访问、电脑不可访问时，再检查云安全组和防火墙是否开放实际 API 端口。

### 会话结束后再次发布一直等待

旧客户端曾在关闭会话页面后留下 SSE 上游连接，导致发布无法确认沙箱空闲。0.3.1 客户端已修复断连清理，并验证了真实会话后再次发布。更新后重启本地 Web，浏览器强制刷新；正在执行中的会话仍需正常结束后才能发布。

## 5. Windows 本地 Web

Windows 安装 Python、Node.js/npm。在 **PowerShell、仓库根目录**执行：

```powershell
python admin_web/build.py --version 0.3.2
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\admin_web\scripts\start.ps1
```

构建安装并编译前端，启动脚本自动创建 Python 环境、安装依赖并打开浏览器。首次安装需联网。终端保持运行，停止按 `Ctrl+C`。

独立包位于 `artifacts/admin_web/0.3.2/admin_web-0.3.2.tar.gz`。在空目录解压，进入包含 `admin_web` 子目录的目录，运行上面的 PowerShell 启动命令即可；独立包不需要源码和 Node.js。

默认页面为 `http://127.0.0.1:18765`。PowerShell 不使用 Linux 的 `sh install.sh`。Linux 本地客户端在构建后使用 `sh admin_web/scripts/install.sh`、`sh admin_web/scripts/start.sh`。

## 6. 第一次使用

1. 本地页面打开连接设置，填服务器地址和**服务器发布目录 .env 的 ADMIN_TOKEN**，点击“保存并测试连接”，测试刚填写的值。
2. 凭据通过但模型未就绪时，进入模型配置，不需要反复更换令牌。
3. 空平台点击 MiniMax 或 GLM 示例，填写 Key、测试并保存，然后发布模型网关。
4. 创建 Agent，选已发布模型、填写指令、启用并发布。确认有生效版本后进入会话。
5. 创建会话，发送消息，再验证一次实际工具操作。

预配置安装成功后可直接选择 Code 或 Data。见[模型配置](model-configuration.md)和[导入导出](import-export.md)。

## 7. 日常管理

在服务器发布目录执行：

```bash
./status.sh
./logs.sh
./stop.sh
./start.sh
```

停止不删除数据，删除发布目录会删除其中的数据。新版本解压到新目录，避免覆盖运行目录。镜像标签来自各模块版本，整包版本来自根 `VERSION`。默认流程使用 IP 入口；域名、HTTPS 和自定义资源配置是额外部署选项。
