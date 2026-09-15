# 本地管理 Web

Windows 源码部署：在仓库根目录 PowerShell 执行：

```powershell
python admin_web/build.py --version 0.3.1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\admin_web\scripts\start.ps1
```

需要 Python 和 Node.js/npm；首次安装需联网。启动脚本自动创建 Python 环境、安装依赖并打开页面。

独立包解压后，在包含 admin_web 子目录的目录执行同一启动命令。独立包只需 Python，不需要 Node.js。终端按 Ctrl+C 停止。

Linux 使用 `sh admin_web/scripts/install.sh` 和 `sh admin_web/scripts/start.sh`，这些不是 PowerShell 命令。

页面默认 `http://127.0.0.1:18765`。连接设置填写服务器地址和服务器发布目录 .env 的 ADMIN_TOKEN，点击“保存并测试连接”。凭据通过但模型未就绪时，进入模型配置，不需要换令牌。

空平台提供 MiniMax、GLM 两个可编辑示例。先测试、保存并发布模型网关，再创建并发布 Agent。导入内容保存为草稿，需要按页面提示完成资源与 Agent 发布。

发布任务未结束时不代表成功，失败原因会显示在当前页面。只有确认生效后再创建会话。
