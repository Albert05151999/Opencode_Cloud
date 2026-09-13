# catalog_service

模型、Agent、Skill、MCP、Hook 的目录、草稿、版本、导入导出与不可变配置编译服务。SQLite 和内容寻址 blobs 只由本服务写入。发布任务和容器操作通过版本化 HTTP 契约交给 operations 与 sandbox_manager。

入口：`python -m catalog_service.main`。`MODULE_CONFIG` 指向渲染后的本模块 JSON；`SERVICE_TOKEN` 必须在部署时注入。`DATA_ROOT` 是本模块数据根目录，不能配置到旧单体或其他服务的数据目录。`/health/live` 为公开存活检查，其他 API 需要内部凭据。

部署配置 `settings` 支持 `model_gateway_public_url`、`agent_runtime_image`、`seed_root`。空 seed_root 使用镜像内资源。初始资源只导入一次，并编译到本服务数据目录；重启不会覆盖页面编辑。模型凭据保存在受限目录的业务数据库中，导出默认脱敏，开启凭据导出需使用相应显式 API。

公开管理路由保留 `/cloud/admin/*` 原目录操作契约。`POST /internal/v1/releases/prepare` 返回不可变 release，`POST /internal/v1/releases/{id}/commit` 条件更新期望版本，重复提交同一 release 幂等。执行服务的已应用版本与目录期望版本分别持久化。`GET /internal/v1/agents/{id}/bundle` 提供含 base64 文件的不可变包；`POST .../authorize` 校验原生调用及模型分配。

Hook 编译和 MCP/Hook 探测仅向 sandbox_manager 提交受约束数据；本镜像不需要 Docker socket。部署和数据迁移命令见根部署指南。升级前备份数据库及 blobs/compiled 目录；数据库备份不能代替资源文件备份。

验证：`python -m pytest test/catalog_service`。测试覆盖旧目录/资源/加密传输行为及不可变发布、条件提交、模型权限契约；实际容器探测需要 Docker 验收环境。
