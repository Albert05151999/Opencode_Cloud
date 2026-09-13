# operations

发布、归档、永久删除、沙箱操作、恢复策略与服务端压测协调服务。仅本服务写入 `operations.db` 中的作业、恢复状态与压测记录；它不挂载 Docker socket，不读取其他模块数据库。

入口：`python -m operations.main`。部署时设置 `MODULE_CONFIG` 与 `SERVICE_TOKEN`，服务 URL 来自本模块配置 `services`。`DATA_ROOT` 指向本模块目录。就绪检查验证目录、沙箱、文件和模型服务连通性。

发布作业持久化 prepare → validate → quiesce → apply → verify → commit 检查点，request_id 在数据库内唯一，同 Agent 的操作与压测共享持久化准入限制。已确认应用后验证失败可做有界补偿；应用请求结果不明确或服务重启进入 `needs_recovery`，不会自动重放破坏性动作。此状态保留准入限制，应先检查对应执行服务状态和检查点；不要删除数据库行以绕过它。

永久删除要求 Agent 已归档、有效的影响预览和完整 Agent ID 确认。影响预览聚合各数据所有者的指纹，执行时各服务再次校验。压测使用保留的 `loadtest-` 用户、公开 session HTTP 契约与原统计格式；清理意图先持久化，再调用各所有者清理，清理中的用户不能重新创建沙箱。

自动恢复保持失败阈值、退避、窗口限额、最大并行度、Agent 开关。仅确认空闲或持有未被新活动推翻的同容器空闲证据才重启；执行状态未知时跳过，压测用户不参与自动恢复。

验证：`python -m pytest test/operations`。覆盖持久化冲突、取消、未知应用结果、补偿、删除预览变化、HTTP 压测和清理后的准入。Docker 端故障恢复与真实模型性能需要完整部署验证。

`POST /cloud/admin/jobs/{id}/reconcile` 携带新的 `request_id`：仅查询到原发布版本已验证、或删除已完整完成等证据时，补记提交并释放准入限制，不重新执行删除/重启。`POST /cloud/admin/jobs/{id}/retry` 仅用于中断的永久删除；先重新获取 Agent 的 delete-preview，再提交新的 `request_id`、`preview_id` 和 `confirmation`。新预览明确确认剩余数据，重试使用新的执行标识并保留尝试历史。旧预览或变更后的指纹返回 409。

所有后台任务保留发起请求的 trace_id/request span；执行使用新的子 span。结构化日志包含 job_id，内部调用传播 traceparent。压测使用 run_id 作为后台关联 job_id；重启记录中断，创建新的事件 span，不能伪造重启前的连续执行。
