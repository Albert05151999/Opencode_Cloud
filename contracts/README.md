# 服务边界与契约

对外接入请使用 [API 使用手册](../docs/api.md) 和 [完整接口参考](../docs/api-reference.md)；本文件说明内部服务归属和一致性约束。

`public_routes.json` 保存迁移时公开接口的归属，用于路由回归；各服务自身 `/openapi.json` 是当前接口结构来源（内部接口需 SERVICE_TOKEN）。内部生命周期协议以 `/internal/v1/` 为版本边界，新增字段保持兼容，破坏性变更必须另开版本。

| 模块 | 唯一写入的数据 | 跨模块调用 |
| --- | --- | --- |
| api_gateway | 无业务状态 | 公开路由 → 所属服务 |
| catalog_service | catalog、资源 blobs、编译版本、发布记录 | model_gateway 测试、sandbox_manager 探测/编译 |
| sandbox_manager | platform.db、lifecycle.db、不可变配置缓存 | catalog 获取/授权、file 分配、operations 准入 |
| file_service | 工作区/state、cleanup.db | operations 准入/清理意图 |
| operations | jobs、压测、恢复策略 | 各执行所有者的内部 API |
| model_gateway | 已激活模型配置与回滚版本 | 模型供应商 |
| observability | 自身日志与日志保留维护 | 共享日志卷，只读业务事件 |
| agent_runtime | 分配给自身的工作区与运行状态 | model_gateway 推理接口 |

发布链：operations 创建持久作业 → catalog 准备不可变版本 → sandbox/model 验证 → sandbox quiesce → 执行所有者 apply → verify → catalog commit → sandbox resume。HTTP 超时不能推断远端未执行；不确定结果进入 needs_recovery，通过版本证据 reconcile，删除重试必须重新核对剩余影响。

每个写服务独占自己的数据库；禁止其他服务直接导入实现、打开数据库或绕过所有者改资源。file_service 分配的工作目录作为数据卷交给同宿主机 Docker 使用，这是明确的数据面共享，不是跨库调用。当前独立部署支持同服务器的独立服务容器；跨服务器沙箱存储调度不属于现有实现。

追踪使用 W3C traceparent、X-Cloud-Request-ID、X-Cloud-Job-ID。缺失或非法追踪 ID 会重新生成；运维日志不能证明所有 span 已采集，查询截断时明确标注。SERVICE_TOKEN 是内部信任域凭据；ADMIN_TOKEN 只用于公共管理入口，MODEL_GATEWAY_TOKEN 仅允许推理。
