# 0.3.0 交付验收

范围说明：本文为 2026-09-11 原交付批次的冻结记录，保留下方原测试数字与边界。随后新增的压测及容量检查不属于这两份 ZIP；最新源码结果和待交付项见 [项目进度](../项目进度.md)及 [06 阶段](../06-load_testing_todolist.md)。

日期：2026-09-11。此版本补齐 Agent 生命周期、沙箱运维、资源迁移和模型配置功能。部署入口仍为根目录 `部署指南.md`；已有 0.2.2 使用 `docs/upgrade-0.3.0.md`。

## 已完成的功能

- Agent 创建、复制、编辑、归档、恢复、空草稿删除及带影响预览的永久删除。
- 沙箱标识搜索、状态与资源采样、会话归属、启动/停止/重启、强制操作确认、空闲异常自动恢复。
- 持久任务、幂等提交、分页记录、取消及重启后检查点对账。
- 原生模型/MCP/Skills 导入；平台配置及加密迁移包；资源历史固定版本和 Agent 模板恢复。所有导入先进入全局草稿池，发布与分配均须显式操作。
- 七家厂商模板、配置示例、隔离草稿调用测试，模型表单到 LiteLLM 与 Agent 原生 JSON 的服务端预览。
- 旧服务器能力提示、管理向导、导入后发布与分配入口。

## 验证记录

| 检查 | 结果 | 可复现入口 |
|---|---|---|
| 后端回归 | 最终 261 项通过，包含非法模板输入 | `python -m pytest -q` |
| 前端编译与状态逻辑 | 通过，9 项状态测试 | `cd web` 后 `npm run build`、`npm test` |
| 浏览器回归 | 15 项通过，模拟远端 API | `npx playwright test`，`WEB_TEST_BASE_URL` 指向本地服务 |
| 真实运维与配置迁移 | 通过 | `scripts/verify-operations-runtime.py` |
| 真实模型/MCP/Skill/Hook | 通过 | `scripts/verify-management-runtime.py` |
| 隔离 LiteLLM 草稿测试 | 通过 | `scripts/verify-draft-model.py` |
| 干净源码构建和打包 | 通过，不依赖旧产物或真实 `.env` | `scripts/verify-clean-source.py` |
| 最终控制器启动与历史会话 | 通过 | `scripts/verify-controller-image.py` |
| 0.2.2 安装迁移 | 通过；历史会话、环境、实例标识保留，导入模型可调用，中断网关任务可恢复 | `scripts/verify-web-upgrade.py --keep-running` |
| Windows Web 真实流式链路 | 通过；凭据保存、配置导入、单次 SSE、工具事件、附件上传下载、执行中发布等待及浏览器页面 | `scripts/verify-windows-companion.py` |
| 解压 Web 包一键启动 | 通过；全新临时目录自动安装依赖、页面启动及资源导入模块完整 | `scripts/verify-web-package.py <web.zip>` |
| 独立 Docker 离线包安装 | 通过；空镜像库安装、冒烟、重启后文件保留、卸载后数据保留 | `scripts/verify-release-package.py <server.zip> --profile coexistence-trial` |

机器可读证据保存在忽略目录 `artifacts/web` 和 `artifacts/release`；脚本可重跑。测试使用自建的独立实例，并清理各自标签下的容器。

离线测试运行在 WSL 中的独立 Docker daemon，采用已有的共存试运行模式。严格预检首次未通过，最终结果不代表此 WSL 宿主满足严格生产准入；默认安装仍保留严格检查。测试容器没有 OOM，实际 swap 使用为 0。验收后仅更新包内说明、OpenAPI 和测试报告，不再修改代码或镜像；最终 ZIP 的 SHA256 以同目录 `package-verification.json` 为准。

## 边界

自动恢复当前与发布共用串行锁，实际并发为 1。未知执行状态不会自动强制重启；中断结果不明确时要求检查重试。永久删除不会回收可能仍被全局资源引用的共享 blob。标准迁移包为 20 MiB 上限，加密包 40 MiB、解密后 20 MiB。迁移包不包含聊天历史与工作区。前端构建仍提示单个 JS bundle 超过 500 kB。

MiniMax、智谱有真实调用证据；其他厂商提供声明式模板与官方示例，没有声称完成账户调用验证。

生产服务器 `ubuntu@106.52.221.61` 的 SSH 返回 `Permission denied (publickey,password)`。未取得可用登录方式，因此没有更新生产服务器；隔离 Docker 与 Windows 验证不能替代该服务器的生产验收。
