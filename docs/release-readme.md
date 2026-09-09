# OpenCode Cloud 0.1.0

此包面向 Linux x86_64、Docker Engine 29.8.0/runc。宿主机需要 Docker Compose、Python 3.11+、bash、zstd 和 unzip；建议至少 16 GiB 内存，最低 8 GiB，保留至少 8 GiB 可用磁盘和 3 GiB 可用内存。镜像已包含，无需在目标机安装 Node、OpenCode 或 Python 应用依赖。

## 安装

解压 ZIP，复制 `deploy/.env.example` 到包外的受保护文件，填入提供商 API key。不要把真实 `.env` 添加到发布包。执行 `sudo bash deploy/install.sh --env-file /absolute/path/provider.env`；默认安装到 `/srv/cloud-agent`。可用 `--root /srv/another-cloud-agent` 指定独立目录。

安装依次验证 SHA-256、加载五个镜像、保留/复制配置、初始化数据目录、执行 doctor、启动模型网关/控制器/Prometheus/Grafana并等待健康。SQLite 模式由控制器启动初始化。再次运行不会覆盖已有配置、Agent 或 `.env`；不同发布版本的升级需要另行评估迁移。

控制器新安装默认 `0.0.0.0:18080`，模型网关 `127.0.0.1:4001` 及 Docker bridge，Prometheus `127.0.0.1:9090`，Grafana `127.0.0.1:3001`。Grafana 用户为 admin，随机密码保存于安装目录 `.grafana-admin-password`，仅 root 可读。身份认证适配器尚未实现，公网入口需通过网络访问限制或有认证的反向代理保护。客户端使用服务器 IP/域名，不能使用 `0.0.0.0` 作为访问地址。

已有安装默认保留监听配置；显式迁移使用 `sudo bash deploy/install.sh --root /srv/cloud-agent --host 0.0.0.0 --port 18080`，会备份配置并保留实例 ID 和数据。仅本机使用可传 `--host 127.0.0.1`。网络部署修订包说明见 `docs/network-release-readme.md`（修订包内为 README）。

## 运维与验证

使用 `bash deploy/{doctor,start,stop,restart,status,logs,uninstall}.sh --root /srv/cloud-agent`。停止/卸载会删除本实例服务和沙箱容器，保留配置、SQLite、工作区、会话状态和监控数据，不执行全局 prune。此版本的 uninstall 撤下运行实例，保留安装脚本和共享镜像缓存以便恢复；如需彻底删除磁盘数据，应在确认备份和其他实例依赖后另行处理。空闲沙箱由控制器按 1800 秒超时、30 秒周期回收，持久数据保留。

实例 ID 在首次安装后固定；修改它会使管理脚本拒绝操作，需恢复原值，防止遗漏旧容器。恢复监控数据时会校正监控卷内文件的服务 UID。控制器属于受信任管理面，持有 Docker socket；虽未挂载密钥文件，仍具备宿主机 Docker 管理权限。

`python3 deploy/smoke.py --output smoke.json` 验证原生会话、隔离、文件和 SSE。加 `--burst` 执行 2 个 Agent × 4 个真实模型请求，需要有效模型 key，会产生正常模型用量。测试只删除自己的会话，报告中列出保留的测试用户文件；容器随后由空闲回收或 stop 清理。

重要参数在安装目录 `config.cfg`，Agent 定义在 `agents/`，模型提供商在 `.env` 与 `config/litellm_config.yaml`。API 契约见 `02_api_contract.md`，架构和测量边界见 `01_architecture.md`。重启保留用户数据；不要手工混用两个安装实例的数据根目录。

## 构建与完整性

开发仓库通过 `scripts/build-release-images.py` 串行构建和冒烟，再通过 `scripts/package-release.py` 导出镜像、生成 checksum 和 ZIP。压缩使用 zstd 两线程、等级 6，ZIP 对已压缩镜像直接存储。镜像身份记录在 `release-images.json`，所有文件哈希在 `checksums.sha256`。固定构建输入不等同于跨日期构建字节完全相同。

本次受控复测：120/120 真实并发请求成功；冷获取 p95 4354.02 ms，热获取 p95 171.14 ms，原生代理开销 p95 76.08 ms；四模型各 20 次配对 TTFT 测量均通过，最大网关增量 p95 71.42 ms。参考机器为 Ryzen 9 8945HS、WSL 可见 15.27 GiB 内存、Ubuntu 24.04、Docker 29.8.0 / runc 1.5.1。

上述性能来自同版源码和冻结运行时的受控测试；独立干净 Docker daemon 的 ZIP 安装、八路真实模型请求、重启、卸载及数据保留为另一个验收环节。最终 ZIP 的通过状态与哈希保存在开发仓库包外 `artifacts/release/final-acceptance.json`，由 `scripts/verify-stage37.py --zip <ZIP>` 校验，不用旧包报告替代新包验证。
