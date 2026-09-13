# 本地管理客户端

客户端包含 React 页面与仅监听 `127.0.0.1` 的 Python 同源代理，所有业务通过网关公开 API 完成。服务器包不构建或安装此模块。

开发：在 `admin_web/frontend` 执行 `npm ci && npm run build`，项目根执行 `admin_web/scripts/install.sh` 和 `admin_web/scripts/start.sh`，访问 `http://127.0.0.1:18765`。`ADMIN_WEB_PORT` 设置本地端口；`ADMIN_WEB_GATEWAY_URL` 设置初始网关地址，之后连接设置由页面保存。Windows 凭据持久化继续使用 Credential Manager，其他平台凭据仅保留在进程内。

打包：`python admin_web/build.py --version 0.3.0`，生成 `artifacts/admin_web/0.3.0/` 归档及 SHA256 manifest。解压后在解压目录执行 `admin_web/scripts/install.sh` 与 `admin_web/scripts/start.sh`。安装脚本默认在解压根目录创建隔离的 `.venv-web`；依赖安装仍需要可访问包源，此客户端归档不包含 Python wheel。

测试：项目根 `python -m pytest test/admin_web/unit`；前端目录 `npm test`。端到端用例位于 `test/admin_web/integration`，需已启动客户端及测试 API。

Windows 解压包可执行 `admin_web/scripts/start.ps1`，沿用独立虚拟环境、依赖哈希缓存及自动打开浏览器；`-NoBrowser` 禁止打开浏览器。通用入口 `python admin_web/scripts/start.py --port 18765 --no-browser` 同样可用。

部署配置：`MODULE_CONFIG` 指向 `config/tooling` 渲染的 `admin_web` JSON，客户端读取 `port`、`data_root` 与 `settings.gateway_url`。`ADMIN_WEB_PORT`、`ADMIN_WEB_DATA_ROOT`、`ADMIN_WEB_GATEWAY_URL` 分别显式覆盖对应值；监听地址始终为本机回环。`.env` 由启动环境显式加载；客户端不自动读取任意工作目录的 `.env`。
