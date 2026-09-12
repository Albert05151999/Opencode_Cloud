# 已部署 0.2.2 时安装 0.3.0

全新安装继续使用根目录《部署指南》。本页仅用于已有 0.2.2 的服务器；0.1.x/0.2.0/0.2.1 不直接跨到 0.3.0。

先按部署指南第 4 节上传 0.3.0 服务器 ZIP 和校验文件。已有 `/srv/cloud-agent/.env` 时无需重新上传或覆盖。开始前停止提交新会话，确认现有生成结束；保留现有 `.env`、管理员令牌和数据目录。

在服务器执行：

```bash
cd /home/ubuntu
sha256sum -c server-upload.sha256
unzip -q cloud-agent-release-0.3.0.zip
cat /srv/cloud-agent/VERSION
# 上一行必须是 0.2.2。以下备份位于安装目录之外。
backup="/home/ubuntu/cloud-agent-before-0.3.0-$(date +%Y%m%d-%H%M%S).tar"
sudo bash /srv/cloud-agent/deploy/stop.sh
sudo tar -C /srv -cpf "$backup" cloud-agent
sudo chmod 600 "$backup"
cd /home/ubuntu/cloud-agent-release-0.3.0
sudo bash deploy/install.sh --root /srv/cloud-agent
sudo bash /srv/cloud-agent/deploy/status.sh
curl -fsS http://127.0.0.1:18080/cloud/health/ready
```

管理数据库首次启动时会在 `data/management/migrations` 中保存迁移前 SQLite 副本。该副本不替代上面的完整安装目录备份。安装保留已有工作区、会话、模型配置和 Agent 固定版本引用；旧运行镜像由已有 Agent 配置继续引用，新的安装使用本批镜像。

服务器就绪后解压本地 `cloud-agent-web-0.3.0.zip` 并运行 `start-web.ps1`，使用已有服务器地址和令牌。确认历史会话、文件、Agent 模型选择和资源版本后再继续使用。

若安装失败，不要删除数据目录或初始化一个空库。先停止本次控制器，保存失败现场，使用安装前备份恢复到独立目录检查，再恢复旧服务；不要将部分旧文件覆盖到运行中的新数据库上。
