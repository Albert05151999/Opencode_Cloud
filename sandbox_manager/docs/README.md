# sandbox_manager：沙箱执行与原生会话路由

独占 Docker 操作、platform.db 路由登记和 lifecycle.db 执行收据；发布先阻断并排空请求，再应用与验证版本，只有 catalog 提交后才解除临时版本。工作目录经 file_service 分配。

配置入口：`config/sandbox_manager/defaults.json`，经 `python -m config.tooling render` 生成配置，运行以 `MODULE_CONFIG` 指定。`python -m sandbox_manager.main` 启动；`/health/live` 检查进程，`/health/ready` 检查就绪（API 入口为 `/cloud/health/ready`）。

依赖：catalog_service、file_service、operations；Docker daemon。独立构建命令：`python -m build_image module sandbox_manager`；命令参数与部署流程见根 `docs/deployment.md`。

日志：`log/sandbox_manager/<instance>/events.jsonl`，轮转由本模块 `settings.logging` 控制。HTTP 与后台作业携带 trace/span/request/job ID；不记录请求正文或凭据。测试位于 `test/sandbox_manager/`。
