# 部署指南

本文命令从仓库根目录执行，除非明确进入了解压后的发布目录。首轮服务器目标为 **Linux amd64、单机 Docker 沙箱**；运行时工作区采用同机共享路径，未实现跨宿主存储调度。

## 1. 配置与构建

部署输入位于 `config/<module_id>/defaults.json`。合并顺序为模块默认值 → `config/profiles/<profile>/overrides.json` → 显式覆盖文件 → 允许的 `CLOUD_<MODULE>_<FIELD>` 环境变量。未知字段、错误类型、无效端口及明文部署凭据会被拒绝。

例如 `config/profiles/production/overrides.json`：

```json
{
  "api_gateway": {"port": 18080},
  "file_service": {"settings": {"max_upload_mb": 512}}
}
```

单模块配置渲染：

```bash
python3 -m config.tooling render api_gateway --profile production \
  --output artifacts/rendered_config/production/api_gateway
# 如需额外部署覆盖，追加 --override /absolute/path/override.json
```

生成的 `config.json` 与 `manifest.json` 包含配置来源、schema 版本及哈希。`service_token` 等敏感字段只允许 `${SERVICE_TOKEN}` 这样的引用，不把实际部署凭据烘焙进镜像。服务通过 `MODULE_CONFIG` 读取自己的渲染结果；数据、日志、端口及绑定地址可通过 `DATA_ROOT`、`LOG_ROOT`、`SERVICE_PORT`、`SERVICE_HOST` 显式设置。

```bash
python3 build_image/build.py module operations --profile production
python3 build_image/build.py bundle --profile production --mode ip
```

构建需要 Python 3 和可用的 Docker Engine。依赖下载发生在构建阶段，目标镜像为 Linux amd64。各模块独立依赖锁不能合并为一个运行环境。默认服务器组合不读取、不构建、不包含 `admin_web`，也不包含 Nginx。

`production` profile 保留交付默认资源：默认 Agent 为 2 CPU / 2048 MiB，普通沙箱启动等待为 15 秒。`acceptance` 和 `acceptance_domain` 是受限虚拟机专用配置，覆盖为 1 CPU / 1024 MiB、启动等待 120 秒；后者还使用测试域名。验收参数只用于降低测试宿主压力和容纳跨架构冷启动，不是生产容量基线。

产物布局：

- `artifacts/contexts/<module>/`：隔离的 Docker 构建上下文。
- `artifacts/rendered_config/<profile>/<module>/`：非明文凭据的配置产物。
- `artifacts/images/<module>/0.3.0/image.tar`：服务器构建工具保存的镜像归档。
- `artifacts/releases/0.3.0/`、`artifacts/releases/release-0.3.0.tar.gz`：安装目录及离线整包。
- `artifacts/scripts/{server,admin_web}/`：执行 `python3 build_image/tools/export_scripts.py` 后集中输出的部署 shell 脚本。

镜像标签使用各模块 `module.yaml` 中的版本；当前模块基线为 `1.0.0`。整包版本只读取根 `VERSION`，当前为 `0.3.0`，修改后归档/目录/manifest 会同步采用新版本。

基础版本统一位于 `config/build_image/versions.json`，构建命令会将 Node、OpenCode、Python、Ubuntu 快照、基础镜像和校验值作为实际 Docker build args 传入；Nginx 镜像也从该文件读取。Dockerfile 不再使用另一套隐藏版本。Python 与 runtime smoke 会校验实际 Python 版本。更新 OpenCode 必须同步更新 `agent_runtime/image/package.json` 和 npm lock；更新 LiteLLM 必须重新生成 `model_gateway/requirements.lock`。中心版本与锁不一致时构建直接报错。Node 版本变更必须同步更新官方归档 SHA256；Python/Ubuntu 变更需同步基础镜像、快照与依赖锁，再进行隔离依赖及 Linux 镜像验证。`--prepare-only` 不运行 Docker，不保存镜像，也不生成安装必需的 `SHA256SUMS`；准备目录不能当作完整交付包安装。

## 2. 离线服务器安装

宿主必须已有 Docker Engine 与 Compose 插件，或在构建时通过 `--docker-materials /path/to/materials` 带入安装材料。材料目录需包含 Linux amd64 的 `docker.tgz`、可执行 `docker-compose` 和对应 `SHA256SUMS`。附带安装器使用 systemd，安装宿主 Docker 需要 root。没有材料且宿主未安装 Docker 时，安装会明确失败，不会联网下载。

离线 Docker 材料不包含 Linux 系统依赖。宿主需先由系统镜像或包管理器提供 `iptables`（含 `ip6tables`）、`procps`（`ps`）、`git`、`xz-utils`、`systemd`、`tar`、`gzip`、`coreutils` 和 `awk`，并由 systemd 启动、挂载 cgroup v1/v2。安装器在写入系统前检查这些条件；缺项时列出需要补齐的命令，不自动联网或设置代理。可先运行 `./install-docker.sh --check-host` 检查宿主。裸 Ubuntu 的系统包准备与之后从离线包安装 Docker/Compose/服务是两个独立阶段。静态 Docker 后续升级需要重新提供已核验材料，参见 [Docker 官方静态安装说明](https://docs.docker.com/engine/install/binaries/)。

将完整归档复制到服务器后：

```bash
tar -xzf release-0.3.0.tar.gz
cd release-0.3.0
./install.sh
./status.sh
```

安装先校验离线文件、加载镜像，再启动 Compose。首次运行生成权限受限的 `.env`，包含三种不同凭据：

- `ADMIN_TOKEN`：公开管理入口和本地客户端连接使用。
- `SERVICE_TOKEN`：服务器内部调用使用。
- `MODEL_GATEWAY_TOKEN`：沙箱推理使用，仅注入模型网关和沙箱管理器。

脚本记录部署绝对路径 `DEPLOY_ROOT`，自动读取 Docker 默认 bridge 网关为 `DOCKER_BRIDGE_IP`。沙箱管理器使用宿主网络并绑定该私有地址；模型网关只发布 Docker 网桥及宿主回环地址，其他内部服务按需发布回环端口。公开 API 默认发布 `18080`。Docker 网桥地址变化后，需要重新设置 `.env` 并重建容器。

工作区和状态目录在宿主与沙箱管理器/文件服务容器内使用相同绝对路径，以便 Docker 挂载正确。不要在安装后直接移动发布目录；迁移路径需同步修改 `.env`、挂载和持久状态。

存活检查为 `/cloud/health`；`/cloud/health/ready` 需要管理员凭据，会报告未就绪依赖。Compose 的启动成功只检查进程存活，不能代替模型调用和沙箱业务验收。

`artifacts/scripts/server/*.sh` 是这些安装脚本的集中副本，**不能直接在该目录执行安装**。请使用完整发布目录内的脚本；如更新脚本，将整套服务器脚本复制到发布目录，与 `compose.json`、`config/`、`images/` 同级后使用。

## 3. 域名与 Nginx

在 profile 中设置域名，然后构建 domain 包：

```json
{
  "nginx": {
    "settings": {
      "domain": "cloud.example.com",
      "certificate": "/etc/nginx/tls/fullchain.pem",
      "private_key": "/etc/nginx/tls/privkey.pem"
    }
  }
}
```

```bash
python3 build_image/build.py bundle --profile production --mode domain
```

解压后、首次启动前，将有效证书和私钥放入发布目录 `config/nginx/tls/fullchain.pem` 与 `privkey.pem`，自行设置 DNS。默认对外发布 `443`，API 网关不再发布宿主端口。当前未实现自动签发或续期。

生成的 Nginx 配置关闭响应及请求缓冲，并设置流式超时与升级头。IP 模式也可接入已有反向代理：转发统一 API 入口，保留流式传输设置。无需改变业务服务路由。

## 4. 初始模型与 Agent 发布

部署配置属于文件输入；运行期间的模型、Agent、Skill、MCP、Hook 和版本属于 catalog 的持久业务状态。不要通过重建镜像覆盖页面编辑结果。全新安装保留默认 Agent、Skill 和 legacy 模型条目，但默认 Agent 与未配置的 legacy 模型初始为禁用；导入并发布 managed 模型后，将默认 Agent 的模型改为该 managed 模型、启用并发布即可。已有 catalog 持久数据不会被此初始化规则改写；已启用但缺少 `CODING_*` 配置的 legacy 模型仍会明确阻止发布。自定义 seed 路径必须显式挂载给 catalog，不能引用未打包的旧根目录。

`config/tooling` 提供显式 seed 导入，不在服务启动时执行。模型 seed 位于 `config/catalog_service/seeds/models.example.json`，其中上游地址、模型名称和 API Key 都是环境变量引用。先复制 `config/catalog_service/.env.example` 为 Git 忽略的 `config/catalog_service/.env`（源码目录已提供无真实密钥的本地模板时直接填写，勿覆盖已有文件），然后填写：

```dotenv
ADMIN_TOKEN=管理接口令牌
SEED_MODEL_BASE_URL=https://模型服务地址/v1
SEED_MODEL_NAME=上游模型名称
SEED_MODEL_API_KEY=上游模型密钥
```

`ADMIN_TOKEN` 只用于请求 catalog 管理接口；三个 `SEED_MODEL_*` 值只进入显式导入的模型配置。dotenv 按数据解析，不执行 shell、命令替换或变量展开。先预览：

```bash
python3 -m config.tooling seed-import models.example.json
```

预览只列出计划导入的 ID，不联网，也不读取 dotenv 或解析实际凭据。取得 `GET /cloud/admin/models` 返回的 catalog `revision` 后，使用公开网关显式导入：

```bash
python3 -m config.tooling seed-import models.example.json \
  --env-file config/catalog_service/.env \
  --catalog-url http://服务器IP:18080 \
  --revision 0 --apply
```

将 `0` 替换为实际 revision。进程环境中的同名变量优先于 dotenv。默认使用 `ADMIN_TOKEN` 认证，也可连接 catalog 的内部地址并显式加 `--token-env SERVICE_TOKEN`。默认拒绝替换已有模型；确需替换时显式加 `--replace`。seed 支持 `templates` 数组，每项形如 `{"template_id":"已有模板ID","agent_id":"new-agent","models":{},"resources":{}}`，调用现有模板恢复接口；模板 ID 从 `GET /cloud/admin/agent-templates` 获取。模板映射遵循该接口契约。

离线发布包已携带独立工具、模型示例和空值 `.env.example`。进入解压后的发布目录，使用下面的入口即可，无需保留源码仓库：

```bash
test -f config/catalog_service/.env || cp config/catalog_service/.env.example config/catalog_service/.env
chmod 600 config/catalog_service/.env
# 编辑 config/catalog_service/.env，填写 ADMIN_TOKEN 和三个 SEED_MODEL_* 变量
./import-models.sh
./import-models.sh --apply --revision 0
```

第一条脚本命令仍是离线预览；第二条才执行导入。将 `0` 替换为实际 revision，需要替换已有模型时再加 `--replace`。脚本默认连接 `http://127.0.0.1:18080`；domain 模式请设置 `API_BASE_URL=https://你的域名`（或追加 `--catalog-url`）。证书须受宿主 Python 信任；私有 CA 可通过 `SSL_CERT_FILE=/absolute/path/to/ca.pem` 指定。内部 catalog 地址须改用 `--token-env SERVICE_TOKEN`，并在该 dotenv 或进程环境提供内部令牌，不能把 ADMIN_TOKEN 当作内部令牌。脚本使用宿主机 Python 3 且仅依赖标准库；需要指定解释器时设置 `SEED_PYTHON=/path/to/python3`。

模型导入是一次 catalog 事务；随后各模板恢复分别提交，失败时工具报告已完成步骤，不自动重试、不假设整份 seed 跨步骤原子化。导入只改变 catalog，**不会发布模型或 Agent**；继续使用下面的发布 API，或在管理页面发布。

首次安装推荐通过管理页面导入资源并发布。也可使用公开 API，以下以管理员 token 环境变量和本地受限 JSON 文件为例：

```bash
export CLOUD_URL=http://服务器IP:18080
read -r -s ADMIN_TOKEN
export ADMIN_TOKEN
curl --fail-with-body -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$CLOUD_URL/cloud/admin/models"
```

准备 `model.json`，填入自己的模型与凭据；文件不提交 Git。可在 `revision` 中填写上一步返回的版本号，防止覆盖并发修改：

```json
{
  "model": {
    "id": "my-model",
    "name": "My model",
    "provider": "openai-compatible",
    "upstream_model": "your-upstream-model",
    "base_url": "https://your-provider.example/v1",
    "api_key": "replace-locally",
    "enabled": true
  }
}
```

```bash
curl --fail-with-body -X PUT -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' --data-binary @model.json \
  "$CLOUD_URL/cloud/admin/models/my-model"
curl --fail-with-body -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -d '{}' \
  "$CLOUD_URL/cloud/admin/models/apply"
```

发布返回持久任务；通过 `GET /cloud/admin/jobs`、`GET /cloud/admin/jobs/<id>` 检查最终状态。随后编辑 Agent 草稿，选择模型，再通过页面或 `POST /cloud/admin/agents/<id>/apply` 发布。资源导入不等于执行环境已生效；必须等待发布任务成功。

旧环境中依赖 `CODING_*` 等变量的 legacy 模型，需要保留相应部署输入或转换为显式管理模型。迁移目录本身不会激活模型网关配置，也不会自动重新执行旧发布任务。

## 5. 独立客户端

源码构建需要 Node/npm，日常运行已构建包只需要 Python 3.11+ 及伴随服务依赖：

```bash
python3 admin_web/build.py --version 0.3.0
python3 build_image/tools/export_scripts.py
```

在客户端解压 `admin_web-0.3.0.tar.gz`，进入包含 `admin_web/` 的目录：

```bash
sh admin_web/scripts/install.sh
sh admin_web/scripts/start.sh
```

`install.sh` 默认在解压根目录创建 `.venv-web` 并安装固定版本依赖，避免写入系统 Python。首次安装需要能够访问 Python 包源；归档本身不包含 wheel。`start.sh` 使用同一环境，环境尚未安装时会明确退出。

默认访问 `http://127.0.0.1:18765/chat`，在连接设置填写服务器 API 地址及 `ADMIN_TOKEN`。客户端通过公开 API 获取日志与 trace，不访问服务器文件系统。

如使用集中输出的脚本：

```bash
export ADMIN_WEB_ROOT=/absolute/path/to/extracted-client
sh artifacts/scripts/admin_web/install.sh
sh artifacts/scripts/admin_web/start.sh
```

`ADMIN_WEB_ROOT` 必须是包含 `admin_web/` 的目录；`ADMIN_WEB_PYTHON` 可指定虚拟环境 Python。`ADMIN_WEB_PORT` 和 `ADMIN_WEB_GATEWAY_URL` 可设置本地端口与默认服务器地址。也可渲染 `config/admin_web`，用 `MODULE_CONFIG` 指向配置文件。

服务器和客户端是两个独立部署入口。服务器必须在完整发布目录运行 `./install.sh`、`./status.sh`、`./start.sh`、`./stop.sh`、`./restart.sh`、`./logs.sh`、`./upgrade-module.sh` 或 `./uninstall.sh`；Admin 客户端在自己的解压根目录运行 `admin_web/scripts/install.sh` 和 `admin_web/scripts/start.sh`。不要从集中导出的脚本目录单独执行服务器安装，也不要把 Admin 安装进服务器容器环境。

## 6. 日志、单模块升级与回滚

日志持久化到部署目录 `log/<module>/<instance>/`，同时输出 stdout。管理页面及 `/cloud/logs`、`/cloud/traces/<trace_id>` 提供授权查询。Agent runtime 的 stdout/stderr 由入口监督进程转换为结构化元数据，写入 `log/agent_runtime/<sandbox_id>/events.jsonl`；只保留流名、字节数、生命周期和退出状态，不保存原始文本、prompt 或凭据。轮转参数为 `config/agent_runtime/defaults.json` 的 `settings.log_max_bytes`、`settings.log_backup_count`，默认每文件 10 MiB、5 个备份。宿主由沙箱管理器准备 UID/GID 10001 可写目录，容器仅挂载自己的日志目录。更新旧沙箱镜像时需要按流程重建容器以添加日志挂载；缺少挂载的旧容器不能通过新的严格恢复检查。

性能排查可从聊天页的“查看调用链”直接进入本次发送的详情，或在管理页“日志与调用链 → 请求调用链”选择最近请求、输入 `trace_id`，也可按 `session_id` 查找同一会话的多轮请求。每次发送独立生成 trace；会话 ID 用于关联多轮，避免把长会话的所有操作混成一个时间轴。

详情展示观测时间范围、模块数、异常阶段和父子时间瀑布。点击模块筛选，点击阶段查看对应日志，“仅异常”用于定位错误；未记录耗时明确显示“未记录”。模块耗时按时间区间并集计算，并行阶段不能相加当作总耗时，最终以客户端 TTFB/总时长及顶层请求为准。HTTP 事件只记录 `method` 和不含查询参数的 `path`；沙箱 `stage_complete` 显示准入、锁等待、配置读取、工作区、Docker 查询/创建/启动、就绪检查耗时。

受管理聊天客户端通过 `messageID=msg_<32位trace_id>` 关联异步推理。运行时系统插件将模型请求传播到模型网关，并根据 assistant parentID 与工具消息记录真实工具执行区间；不记录 prompt、工具参数、输出或凭据。模型派发本身是瞬时事件，工具阶段没有可靠父跨度时独立显示，不伪造父子关系。其他 API 客户端只发送 HTTP trace 头而不使用该消息关联约定时，不能保证异步模型、工具段继承同一 trace。平台记录不代表供应商内部或全部 OpenCode 内部执行过程；旧日志不会自动补齐新增跨度。

升级追踪功能需要更新后台镜像及 Agent runtime，并重新发布受影响的 Agent，让后续沙箱加载新版系统插件；仅刷新前端不会升级已有容器。普通 runtime stdout/stderr 仍只保留结构化元数据，只有受限系统事件前缀经字段白名单校验后写入模型/工具追踪记录。

功能验收通过不等于性能达标。冷启动应以新用户首次请求计时；热请求与绑定会话分别记录样本数、p50/p95/max，并单独测并发。当前性能目标为冷启动小于 4 秒、热请求小于 300 毫秒；供应商推理和工具时间需另报。可复用真实环境基准脚本 `test/performance/benchmark.py`，通过 `--url` 和 `--token-file` 指定服务器，使用独立测试用户，不调用模型，结束仅停止本轮沙箱。


追踪查询在保留日志内有界扫描，默认最多 100 个文件、64 MiB；范围由 `config/observability/defaults.json` 控制。页面显示扫描范围与截断状态，`truncated`/`partial` 表示扫描不完整；未截断也不代表超出日志保留窗口或未埋点阶段存在记录。无法传播的第三方追踪段不应视为完整调用链。

```bash
./logs.sh api_gateway
./restart.sh operations
./stop.sh
./start.sh
```

升级一个服务前准备对应镜像归档，并保留旧镜像标签与归档：

```bash
./upgrade-module.sh operations opencode-cloud/operations:1.0.1 /path/to/operations-1.0.1.tar
```

模块覆盖记录持久保存在 `image-override-operations.json`，以后启动仍使用选定镜像。使用同一命令指定旧标签/归档可恢复镜像；数据库不兼容时必须先恢复备份，不能仅换镜像。`agent_runtime` 也支持独立升级：

```bash
./upgrade-module.sh agent_runtime opencode-cloud/agent_runtime:1.0.1 /path/to/agent-runtime-1.0.1.tar
```

脚本先加载并确认目标镜像标签存在，再持久化覆盖；runtime 覆盖同步修改 catalog_service 与 sandbox_manager 的 `AGENT_RUNTIME_IMAGE` 并重建这两个服务。它不直接停止已有沙箱；通过 operations 发布相关 Agent，使未来编译版本和受控更新采用新 runtime。回滚 runtime 使用相同命令选择旧标签，再按业务流程发布。所有模块升级在写入覆盖前都会检查目标标签，检查失败保留原覆盖。

`./uninstall.sh` 停止并移除 Compose 容器/网络，保留数据、日志、凭据及镜像。

## 7. 旧数据迁移

迁移工具读取旧部署的数据根，预期有 `management/catalog.db`，可选 `platform.db`、`workspaces/`、`state/`。先预览：

```bash
python3 build_image/tools/migrate_legacy.py \
  --source /srv/old-cloud-data --destination /srv/new-release/data
```

停止旧、新服务及旧沙箱，确认目标不存在或为空后：

```bash
python3 build_image/tools/migrate_legacy.py \
  --source /srv/old-cloud-data --destination /srv/new-release/data \
  --apply --services-stopped --copy-workspaces
```

工具保留原始来源，在目标中备份 management 与 platform 数据；catalog 保留资源及版本，执行任务、压测和恢复状态转入 operations，注册表转入 sandbox_manager。进行中的任务标记为待恢复，不自动重放。编译资源分别保留给 catalog 与沙箱管理器读取。

不传 `--copy-workspaces` 时，工作区/状态继续使用原位置，必须按 `migration-report.json` 的 `runtime_overrides` 修改实际挂载与服务环境；生成的默认 Compose 不会自动采用外部原路径。原数据根之外的路径、既有容器与镜像、凭据需要人工核对。上线前显式发布模型并验证 Agent，检查待恢复任务。恢复旧版本前停止新服务；需要回滚数据时使用备份，不进行双写。

## 8. 验证与交付门槛

无需 Docker 的隔离依赖验证：

```bash
# 需要 uv，可联网下载独立锁定依赖
python3 build_image/tools/verify_dependencies.py

# 创建开发验证环境；各服务生产环境仍分别使用模块锁文件
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e '.[test]'
.venv/bin/python -m pytest test
```

完整离线包生成后可独立检查库存与校验和：

```bash
python3 build_image/tools/verify_release.py artifacts/releases/0.3.0
```

本轮交付验证已经完成以下真实路径：

- 在 amd64 构建环境生成 8 个 Linux amd64 镜像，runtime image smoke 验证 UID 10001、Node、OpenCode、Python、办公文件依赖与目录读写。
- 在全新的 Ubuntu x86_64 主机安装静态 Docker/Compose，并从完整无源码归档离线加载和启动服务器；安装器包含 Docker daemon 就绪等待。
- IP 模式经局域网 `:18080` 验证；domain 模式使用测试证书完成 HTTPS、SSE 与反向代理路径验证。
- 使用可控 OpenAI 兼容协议服务执行完整模型网关、OpenCode、工具回传、SSE、文件、压测、停止/恢复和跨服务 trace 流程。该协议服务是真实网络进程，不是路由 Mock，但不是商业模型供应商。
- Admin 客户端从独立归档创建隔离 `.venv-web`、启动 loopback companion，并通过 Playwright 连接真实局域网服务器；日志页面取得 7 个模块、100 条实际日志及包含 2 个 span / 2 个事件的 trace。
- Ubuntu root 完整 Python 回归为 392 passed、1 skipped；唯一 skip 是 controller 环境不安装 LiteLLM，独立 LiteLLM 环境的 model gateway 测试为 4 passed、0 skipped。
- Ubuntu 整机重启后 Docker 与 7 个 Compose 服务自动恢复；原会话消息与文件哈希、Agent active version、任务状态和 catalog revision 保持一致，并能在原沙箱上继续完成新的工具调用。
- `catalog_service` 已执行单模块回滚再前滚；仅该容器被替换，API gateway、file/model/observability/operations/sandbox manager、Agent runtime 沙箱均未重建，catalog revision、工具结果与文件哈希保持不变。

真实安装也暴露并修复了四类仅靠 mock 难以发现的问题：全新 catalog 的 legacy 模型和默认 Agent 现在初始禁用，不会阻塞首个 managed 模型发布；沙箱健康 probe 使用隔离运行时可达地址，工作区与 runtime 日志使用宿主绝对路径挂载；静态 Docker 安装等待 daemon 真正 ready 后才继续；POSIX Admin 安装不再向系统 Python 写包，而是创建隔离 venv。已有 catalog 状态不会被新的初始化默认值静默改写。

可重复执行的主要检查：

```bash
# 源码测试环境
.venv-controller/bin/python -m pytest test

# Ubuntu root 测试使用独立 controller venv；LiteLLM 使用另一环境
.venv-linux-controller/bin/python -m pytest test -rs
.venv-linux-litellm/bin/python -m pytest test/model_gateway

# 无源码发布包库存与哈希
python3 build_image/tools/verify_release.py artifacts/releases/0.3.0

# Admin 真实局域网浏览器；token 通过环境注入，不写入命令记录或证据
ADMIN_WEB_RELEASE_ROOT=/absolute/path/to/extracted-admin \
ADMIN_WEB_ACCEPTANCE_TOKEN='<ADMIN_TOKEN>' \
node test/system/admin_web_real_smoke.mjs http://服务器IP:18080
```

交付的模型 seed 与 `.env.example` 不包含真实密钥。部署者仍需提供自己的 provider URL、模型名和 API key，显式导入并发布。后续已在重新安装的 Ubuntu 中将真实供应商接入完整部署链：MiniMax-M3 通过完整流程（含单用户压测及显式 cleanup），GLM-5.3 通过基础链并刻意不重复压测。两者均完成真实 bash/Python 求和 5050、SSE、文件往返、沙箱停止/启动及跨服务 trace。

独立打包的 Admin 已通过真实供应商局域网浏览器验收；Ubuntu 整机重启后，原会话恢复并再次完成工具调用；严格验证 CA 与域名的 Nginx HTTPS 入口在原会话新增工具调用得到 42，trace 查询通过。发布目录模型 seed CLI 导入与受管理沙箱安全属性也通过。证据为 `artifacts/verification/real-system-{minimax,glm,restart,domain,security,seed-import}.json` 和 `artifacts/verification/admin_web/real-provider-lan-smoke.json`。

本轮复用此前构建并验证的生产镜像，仅在临时验收部署覆盖为 1 CPU / 1 GiB、启动等待 120 秒；没有重新构建镜像或重跑全部单元测试。此前 Linux 全量测试 403 项通过，主环境跳过的 1 项 LiteLLM 测试已在独立环境补测通过。此前单模块回滚、Nginx 日志轮转与优雅退出及首轮环境清理报告仍是对应轮次的证据；本轮 Ubuntu 虚拟机、临时数据和虚拟机工具已销毁，测试端口已关闭，清理证据见 `artifacts/verification/real-system-cleanup.json`。

Nginx 实测使用受信任的测试 CA，通过 HTTPS 取得包含 nginx、api_gateway、catalog_service 的 trace；日志未包含查询参数标记或 ADMIN_TOKEN。轮转后新文件持续写入，保留数量符合配置；轮转是定期检查，文件大小可能在两次检查之间超过阈值。SIGQUIT 在 10 秒停止期限内完成并返回退出码 0，重启后入口恢复健康。证据见 `artifacts/verification/nginx-logging.json`。

普通沙箱创建默认设置 `cap_drop=ALL` 和 `no-new-privileges`，保持 UID 10001、只读根文件系统与资源限制。旧容器不会因升级 manager 自动改变创建属性；通过 `POST /cloud/admin/sandboxes/<id>/restart` 提交带 `request_id` 的正常运维重建，等待任务成功，可保留工作区、状态与会话。本轮已实际验证重建后的安全状态为 ok，原会话和文件哈希保持一致，并继续执行新的工具调用。证据见 `artifacts/verification/seed-cli-security.json`。

受管理沙箱的安全状态可通过 `/cloud/operations/security-status` 查看，包括实际容器权限、只读根文件系统、网络模式、capabilities 和资源限制。缺失证据返回 unknown；这不是宿主机完整漏洞扫描。各服务 `/metrics` 使用对应服务凭据，公共入口 `/metrics` 使用 ADMIN_TOKEN。

## 2026-09-13 性能修复补丁

已安装0.3.0的服务器可解包 `artifacts/releases/performance-2026-09-13.tar.gz`，执行其中 `sh install.sh /srv/cloud-release/release-0.3.0`。脚本校验内容后仅升级api_gateway、sandbox_manager、file_service，保留原覆盖配置以供回滚，不重建用户Agent容器。原0.3.0归档仍是历史交付；从当前源码重新构建则包含修复。

实际性能和测量边界见 `artifacts/verification/performance/README.md`。本机跨架构 QEMU 尚未达到阈值；原生服务器的后续对照结果见下节，不能混用两种环境的数据。

## 原生服务器性能验收补充（2026-09-14）

已在用户提供的 4 核 / 8 GB 原生 Ubuntu 上隔离对照旧版、未修复重构版、修复版。修复版三轮冷启动 1.78–2.11 秒、热 p95 40–46 ms、4 并发 p95 117–130 ms，所有热样本低于 300 ms；真实模型请求确认 88 ms，工具及回复 4.59 秒，工具/SSE/清理通过。完整口径及原始证据见 [原生性能报告](../artifacts/verification/performance/native/README.md)。本机跨架构 QEMU 的 27 秒冷启动结果仍保留，不能代表原生 Linux 的部署性能；当前测试也不代表最大承载容量。
