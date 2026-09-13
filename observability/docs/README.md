# observability：模块日志与调用链查询

读取 LOG_ROOT 下各模块 `events.jsonl`，`/cloud/logs` 支持 module、job_id、trace_id 筛选。`GET /cloud/traces` 按 trace_id 或 session_id 列出最近请求，并从 API gateway 入口补充 method、path、duration_ms、message_id 和 operation；默认 `exclude_health=true` 隐藏纯健康、metrics 和可观测性自查询，可显式关闭。`GET /cloud/traces/{trace_id}` 返回按 span_id 聚合的 spans、span_tree、原始 events 和 summary。未知时长为 null，模块耗时按已知 span 区间并集计算。外部父 span 会标记 `external_parent`，不据此判断缺失。

扫描由 `settings.trace_scan_files`（默认 100）和 `settings.trace_scan_bytes`（默认 64 MiB）共同限制。响应的 coverage 说明实际扫描文件、字节和 retention_days；partial/truncated 表示扫描或结果被截断。即使两者为 false，completeness 也只保证已扫描的保留日志范围，不表示端到端 trace 完整。每小时清理超过 retention_days 的轮转文件，保留当前活动日志。

配置入口：`config/observability/defaults.json`，经 `python -m config.tooling render` 生成配置，运行以 `MODULE_CONFIG` 指定。`python -m observability.main` 启动；`/health/live` 检查进程，`/health/ready` 检查就绪（API 入口为 `/cloud/health/ready`）。

依赖：共享日志卷；不读取其他模块数据库。独立构建命令：`python -m build_image module observability`；命令参数与部署流程见根 `docs/deployment.md`。

日志：`log/observability/<instance>/events.jsonl`，轮转由本模块 `settings.logging` 控制。HTTP 与后台作业携带 trace/span/request/job ID；不记录请求正文或凭据。测试位于 `test/observability/`。
