# 源码构建与清理状态（2026-09-09）

## 已完成

- `package-web-release.py` 改为调用源码打包流程，不读取 `artifacts/release/final/cloud-agent-release-0.1.0`。
- 镜像构建自动拉取固定摘要的 LiteLLM、Prometheus 和 Grafana；修复独立运行控制器验证脚本时的模块导入路径。
- 增加 `scripts/build-from-source.sh`，覆盖前端、单元测试、镜像验证及两份交付 ZIP；拒绝使用版本不匹配的旧镜像报告。
- `.gitignore` 排除 artifacts、虚拟环境、node_modules、dist 和测试缓存；`.gitattributes` 确保 shell 脚本在 Windows clone 后仍使用 LF。
- README 和部署指南说明全新 clone 的构建入口、首次安装、凭据准备及重新构建的哈希处理。

## 实际验证

- Linux 单元测试：217 项通过。
- runtime 镜像构建与正常/只读运行、离线原生搜索验证通过。
- LiteLLM 使用本地模拟提供商的调用、并发流式、故障切换验证通过。
- controller 镜像验证通过。
- 源码打包的两份 ZIP：文件 SHA256、ZIP CRC 和秘密扫描通过。
- 另建不含 artifacts、真实 `.env`、node_modules、dist、虚拟环境的源码副本：`npm ci`、TypeScript/Vite 构建通过；仅提供本次镜像构建生成的报告，独立生成服务器和 Web ZIP，通过完整性检查。使用已有 Docker 镜像缓存，未声称从无缓存网络环境完成构建。
- Windows 下从新 Web 包加载 `/chat`、`/admin`、`/local/bootstrap`：全部返回 200，未读取用户保存的凭据。

本次没有访问或升级公网服务器。旧有 `web-v0.2.2` 交付物未覆盖，根目录部署指南中的原 SHA256 仍对应这些包。

## 尚未完成的磁盘删除

自动审批先后拦截了批量删除及用户确认后的旧 Ubuntu 备份单独删除，工具仅返回 `blocked by policy`。旧包和备份仍在磁盘上，不能将清理标记为完成。

旧发布目录已不再是正常源码构建依赖，可以退役；旧版升级回归脚本若要重跑，需另行提供相应历史夹具。`.gitignore` 不会取消已经被 Git 跟踪的文件；当前工作目录没有 `.git`，因此本次未执行索引清理、提交或实际 clone。
