# OpenCode Cloud 0.1.0 网络部署修订 1

历史范围：以下记录仅适用于 0.1.0 网络修订包，不是最新安装入口。当前使用[部署指南](../部署指南.md)。管理安装已有单管理员 Bearer；下文无认证描述属于旧包，`auth.enabled` 对应的旧 JWT 方案仍未实现。详见[项目进度](../项目进度.md)。

这是包含五个原有镜像的完整离线包。应用镜像与原始最终交付包相同；本次修改的是宿主机部署脚本、默认配置和终端客户端，没有重新构建应用镜像。包内 `deployment-revision.json` 记录基包清单哈希。

## 新安装

在 Linux x86_64 服务器解压，准备包外的提供商环境文件，然后执行：

```bash
sudo bash deploy/install.sh --env-file /absolute/path/provider.env
```

默认安装目录 `/srv/cloud-agent`，控制器默认监听 `0.0.0.0:18080`。如该端口被占用，可以加 `--port 其他端口`；需要仅本机访问时加 `--host 127.0.0.1`。不要把 `0.0.0.0` 当作客户端访问地址，应使用服务器 IP 或域名。

宿主机需要 Python 3.11+、Docker Compose、bash、zstd、unzip。严格预检要求 Docker 29.8.0+、至少 8 GiB 内存及足够空闲资源。已有安装的 `.preflight-profile=coexistence-trial` 保留并继续生效，允许此前显式选择的 Docker 29.7.2 共存试运行条件；新安装不会自动降低预检要求。

模型网关仍只绑定 loopback 和 Docker 网桥，Prometheus/Grafana 仍只绑定 loopback。身份认证尚未实现：API 可执行命令和访问用户文件，直接对公网开放需要由网络访问限制或有认证的反向代理保护。`auth.enabled=true` 仍不受支持，不能用它启用认证。公网端口是否可达由实际安全组、防火墙和地址映射决定。

## 已有 0.1.0 安装

从本次解压目录运行以下命令，更新部署工具，并显式迁移监听地址和端口：

```bash
sudo bash deploy/install.sh --root /srv/cloud-agent --host 0.0.0.0 --port 18080
```

已有 `.env` 会继续使用，无需再次传递。修改配置前自动创建 `config.cfg.before-listener-*` 备份；保留实例 ID、工作区、会话数据、提供商配置和预检模式。命令可能重新创建控制器，会短暂中断请求。未提供 `--host/--port` 时继续保留已有监听配置。跨应用版本迁移不在本修订范围内。

修正后的 doctor 接受 `0.0.0.0`，避免手动开放监听后管理脚本仍拒绝启动。端口预检使用所有 IPv4 网卡检测占用。

## 查看执行结果

在自己的电脑安装 Python 3.11+ 和 httpx，然后执行：

```bash
python -m pip install httpx
python scripts/sse-chat.py --base-url http://服务器IP:18080
```

它创建新会话并实时显示回答和工具状态；默认请求执行 `pwd` 和 Python 求和，会使用模型额度。实际地址用 `--base-url` 指定，也可以编辑脚本开头 `BASE_URL`。会话 ID 输出到终端，历史消息可通过 `GET /session/{id}/message` 获取，生成文件通过 `/cloud/files/list` 和 `/cloud/files/download` 获取，参数见 API 契约。

健康检查：`curl http://服务器IP:18080/cloud/health`；完整就绪检查：`curl http://服务器IP:18080/cloud/health/ready`。通常无需 SSH 隧道；通过域名 HTTPS 使用时需配置有效证书、访问控制和 SSE 代理参数。本修订不修改现有 Nginx。

## 校验和验证边界

解压后在包根目录执行 `sha256sum -c checksums.sha256`。本次部署修订的报告在 ZIP 旁 `verification.json`；原有性能及干净安装验收属于原始 0.1.0 镜像交付，不能当作本次修订重新完成的全量验收。架构和 API 契约文档保留原镜像版本说明，其中旧默认 loopback 的描述由本 README 的新安装默认值替代。
