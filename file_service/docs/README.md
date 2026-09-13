# 文件服务

`python -m file_service.main` 启动工作区文件服务；依赖固定于 `requirements.lock`。服务独占工作区分配、上传下载、文件清理与自己的 `cleanup.db`，通过 HTTP 查询 operations 的准入和清理授权，不读取其他模块数据库。

部署输入由 `MODULE_CONFIG` 指定，包含 `data_root`、`log_root`、`services.operations`、`settings.workspace_root`、`settings.state_root`、上传/用户容量限制。`WORKSPACE_ROOT`、`STATE_ROOT` 可显式覆盖共享卷挂载位置。入口使用 `SERVICE_TOKEN` 内部认证；真实用户授权由 API 网关负责。

公开接口为 `/cloud/files/upload`、`/download`、`/list`。内部 `/internal/v1/workspaces/allocate` 返回由文件服务确认的共享卷路径。目录初始化及上传与清理使用同 Agent 锁；operations 正在删除或清理压测用户时拒绝新的写入。

Agent 清理调用 `/internal/v1/agents/{aid}/cleanup`，提供 `request_id`、最新 `expected_fingerprint`，可选 `empty_only`。用户清理提供 `run_id` 和 `request_id`。清理前向 operations 核对有效意图，写入持久收据后执行。相同请求返回原结果，不会删除后来重建的文件；参数冲突或中断收据返回 409，必须核对实际结果。文件和沙箱按单机共享持久卷契约部署，不提供跨主机路径同步。

验证：`python -m pytest test/file_service`，覆盖路径限制、上传容量、流式下载及清理与上传并发、指纹复核和响应丢失重放。
