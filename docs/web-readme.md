# OpenCode Cloud Web 0.2.2

0.2.2 新增配置 JSON 预览。管理页顶部“全局 JSON”展示全局资源和脱敏的模型网关文件；Agent 的“配置预览与版本历史”分别展示已生效 opencode.json 与已保存草稿。编辑表单下方实时显示 JSON，可复制。Agent 表单调用只读服务端编译器；MCP、Skill、Hook 表单显示待绑定片段，模型表单区分 LiteLLM 条目与 Agent 模型声明。全局资源库本身不是一份会直接加载的 opencode.json。升级此功能需同时更新服务器和本地 Web。

0.2.1 将会话目录绑定放到服务端初始化：实际默认 cwd 与上传/下载目录统一为 `/workspace/sessions/<id>`，无需手动 cd 或目录 Hook。保留 ui-r1～ui-r3 的前端修复。如果曾按旧说明安装 `session-workspace` Hook，请先在 Agent 中移除该绑定并发布，避免旧 Hook 重复拼接会话目录；不要删除其他业务 Hook。

已有会话在下一次执行前检查并绑定，ID、历史与附件保留；绑定不搬移根目录或拼错 ID 目录中的旧文件。对应修复说明与验证记录见 `artifacts/web/session-binding-verification.json`。

Windows 本地聊天与管理页，入口 `http://127.0.0.1:18765/chat`。服务端升级后，聊天、模型导入、Agent 配置、资源上传与发布全部通过 API 完成。

## 本机运行

升级本地包前先停止旧 Web 终端（Ctrl+C），再从新版本解压目录启动；已保存的连接和 Windows 凭据保留。

需要 Windows、Python 3.11+。在项目根目录，或解压后的 `cloud-agent-web-0.2.2` 目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-web.ps1
```

首次启动创建 `.venv-web` 并下载 Python 依赖；以后直接启动。包内已含编译前端，日常不需要 Node.js。终端保持运行，按 Ctrl+C 停止。端口冲突可加 `-Port 18766`。

进入管理页 → 连接设置：服务器 `http://106.52.221.61:18080`，粘贴升级时生成的管理员凭据，勾选保存到 Windows Credential Manager，然后保存、测试连接。凭据不写入浏览器 localStorage 或配置 JSON。HTTP 是明文传输，界面持续标记这个边界。

本地地址设置保存于 `%LOCALAPPDATA%\OpenCodeCloudWeb\connection.json`，仅含服务器 URL。Windows 凭据目标为 `opencode-cloud-web`，用户名为服务器 URL。不要把模型 API key 填到管理员凭据框。

## 上传服务器升级包

在本地项目根目录的 PowerShell 执行。ZIP 和 `.env` 都上传到 `/home/ubuntu`：

```powershell
$server = 'ubuntu@106.52.221.61'
$bundle = '.\artifacts\release\web-v0.2.2\cloud-agent-release-0.2.2.zip'
scp $bundle '.\deploy\.env' "${server}:/home/ubuntu/"
if ($LASTEXITCODE -ne 0) { throw '上传失败' }
ssh $server
```

登录服务器后，在 Ubuntu 终端粘贴：

```bash
cd /home/ubuntu
chmod 600 .env
unzip -q cloud-agent-release-0.2.2.zip
cd cloud-agent-release-0.2.2
sudo bash deploy/install.sh --root /srv/cloud-agent --env-file /home/ubuntu/.env --host 0.0.0.0 --port 18080
sudo bash /srv/cloud-agent/deploy/status.sh --root /srv/cloud-agent
sudo cat /srv/cloud-agent/data/admin-token
```

最后一条仅用于把新生成的管理员凭据复制到本机连接设置，请不要把其输出贴到日志或分享。安装器保留原 `.env`、instance ID、会话、状态和工作区；已安装实例优先使用 `/srv/cloud-agent/.env`，上传的 `.env` 仅在首次安装时复制。0.1.0 → 0.2.1 为支持的升级路径。升级会重建控制器与模型网关，请等当前对话结束后执行；日常 Agent 发布会自动排空任务。

安装前可备份控制面文件。不要在线复制 SQLite 的单个 `.db` 文件作为完整备份；需要数据备份时应停止平台后备份整个 `data`、`state` 与 `workspaces`。

```bash
sudo bash /srv/cloud-agent/deploy/stop.sh --root /srv/cloud-agent
sudo tar -C /srv -czf /home/ubuntu/cloud-agent-before-web.tgz cloud-agent
sudo chmod 600 /home/ubuntu/cloud-agent-before-web.tgz
```

备份包含凭据，不要上传到公开位置。备份后继续运行上方安装命令启动新版本。首次安装无需此备份步骤。服务器仍需原部署要求：Ubuntu 24.04、Docker Compose、Python 3.11+、zstd、已冻结镜像所需资源。

## 日常配置流程

1. 模型 → 从本机导入：扫描常见 Windows OpenCode 路径，也可指定目录或 JSON/JSONC 文件。每次选择一份来源，检查错误与同名冲突；只导入模型，不自动迁移扩展。环境变量、配置引用文件和 API-key 认证文件在本机解析，预览只显示遮罩。
2. 保存模型 → 发布模型网关 → 测试模型 → Agent 配置中勾选允许模型并指定默认/小模型 → 发布 Agent。新模型不会自动分配。
3. MCP、Skills、Hook 各自保存草稿并发布版本，再到 Agent 绑定。全局资源不会自动加载；更新资源后须显式选择新版本并发布 Agent。
4. 命令 MCP 的可执行文件应已存在于运行镜像；工作目录在 `/workspace` 下，不自动安装。全局 MCP 测试时选择目标 Agent；测试使用独立沙箱。
5. Skill 入口只接受 `SKILL.md` 或单 Skill ZIP。聊天附件入口只上传到工作区，不会安装 Skill。
6. Hook 编辑 `.js`、`.mjs`、`.ts` 原生插件。保存草稿持久化；发布执行静态检查及隔离加载。Agent 中按绑定顺序加载，平台 trace Hook 受保护。
7. 发布记录显示等待、验证、应用与失败原因。Agent 有效配置中可回滚历史版本；回滚形成一个新的不可变版本。120 秒仍有任务时发布失败并保留草稿，不强制中断模型任务。

新建或复制 Agent 先选择模型、保存，再发布。停用也需发布才生效，历史会话和文件仍可查看。复制会复制配置和已绑定私有资源，保留全局版本引用，不复制运行容器、会话、工作区。

## Python SSE 客户端

同一个本地虚拟环境能读取 Web 保存的 Windows 凭据：

```powershell
.\.venv-web\Scripts\python.exe .\scripts\sse-chat.py --base-url http://106.52.221.61:18080
```

也支持 `CLOUD_AGENT_ADMIN_TOKEN` 环境变量或 `--token-file`；不要把密钥写进脚本。升级之前的旧服务没有管理接口，无法使用新版管理页。

## 接口与实现

服务器 `/openapi.json` 使用 Bearer 认证，可通过本地代理 `/remote/openapi.json` 下载。完整端点、请求体与 curl 示例见 `02_api_contract.md`。服务端管理数据位于 `data/management`，使用 SQLite 和不可变资源目录，不引入数据库服务。

前端开发：`cd web; npm ci; npm run dev`（需另启本地 Python 服务）。发布前执行 `npm run build`。单元与真实运行证据见 `artifacts/web/final-assessment.md`。

首版不包含多用户、WSL 自动扫描、HTTPS 部署、MCP OAuth、依赖自动安装、任意 npm 插件安装、宿主机 Hook。Windows 本机服务只监听 loopback。
