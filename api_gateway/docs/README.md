# api_gateway：公共 API 入口

将已有公开路由分发到所属服务，保持原生会话与 SSE 流式传输；管理令牌只在入口校验，内部请求使用服务令牌。无业务数据库。

配置入口：`config/api_gateway/defaults.json`，经 `python -m config.tooling render` 生成配置，运行以 `MODULE_CONFIG` 指定。`python -m api_gateway.main` 启动；`/health/live` 检查进程，`/health/ready` 检查就绪（API 入口为 `/cloud/health/ready`）。

依赖：catalog_service、sandbox_manager、file_service、model_gateway、operations、observability。独立构建命令：`python -m build_image module api_gateway`；命令参数与部署流程见根 `docs/deployment.md`。

日志：`log/api_gateway/<instance>/events.jsonl`，轮转由本模块 `settings.logging` 控制。HTTP 与后台作业携带 trace/span/request/job ID；不记录请求正文或凭据。测试位于 `test/api_gateway/`。
