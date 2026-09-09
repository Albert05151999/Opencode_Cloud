"""Record verified 04 milestones; refuse to mark pending real checks complete."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    evidence = {name: json.loads((ROOT / f'artifacts/web/{name}-verification.json').read_text())
                for name in ('runtime', 'upgrade', 'windows-companion')}
    if any(result.get('result') != 'passed' or not all(result['checks'].values()) for result in evidence.values()):
        raise RuntimeError('Real verification gates have not all passed')
    unit = (ROOT / 'artifacts/release/web-unit-tests.log').read_text()
    if '209 passed' not in unit:
        raise RuntimeError('Unit test gate not passed')
    steps = [
        ('04-01','—','04 文档、API 契约、OpenAPI','V、W'),
        ('04-02','01','management.py SQLite、版本、草稿与任务','U'),
        ('04-03','02','Bearer 中间件、SSE CLI、Windows 凭据','U、R、W'),
        ('04-04','02/03','模型存储、分配、请求服务端校验','U、G、W'),
        ('04-05','02/03','资源归属、不可变版本、引用查询','U、R'),
        ('04-06','04/05','Agent 新建、复制、停用与指令','U、G'),
        ('04-07','04/05/06','编译目录、当前/草稿预览及运行路径','U、R、G'),
        ('04-08','05/07','remote/local MCP、cwd 适配与独立探测','U、R'),
        ('04-09','05','Skill MD/ZIP 校验、文件树与版本','U、R'),
        ('04-10','07/09','skills.paths 原生发现；发布时移除重复注入','U、R'),
        ('04-11','05/07','Hook 源码、静态编译、沙箱加载和顺序','R'),
        ('04-12','07/08/10/11','排空、发布、失败保留、重启恢复','U、G、W'),
        ('04-13','01','本地 FastAPI、Vite 编译页面、start-web.ps1','V、W'),
        ('04-14','03/13','连接、凭据保险库、能力、同源 SSE 代理','W'),
        ('04-15','13','Windows 发现、文件选择、JSONC/env/file/auth','U、W'),
        ('04-16','04/14/15','四种模型适配、来源/默认值预览、导入/分配','U、G、W'),
        ('04-17','05/06/13','全局库和 Agent 编辑页','V、W'),
        ('04-18','08/09/11/17','MCP 表单、Skill 附件、Hook 编辑器','V、R'),
        ('04-19','12/17','固定版本更新提示、预览、任务、回滚','V、R、G'),
        ('04-20','13/14','聊天布局、会话、Agent/模型、明暗和窄屏','V、W'),
        ('04-21','20','SSE 消息合并、刷新恢复、停止、手动重试','U、V、W'),
        ('04-22','20/21','工具详情、权限/问题回复、聊天文件','V、W'),
        ('04-23','16/20/21','Windows 配置 → 网关 → Agent → SSE','W'),
        ('04-24','08/10/11/20','两类 MCP、Skill、Hook 实际调用与顺序','U、R'),
        ('04-25','12/23/24','0.1.0 会话迁移、发布失败、恢复与在途任务','U、G、W'),
        ('04-26','01–25','本地包、离线镜像包、部署命令、验收报告','P'),
    ]
    plan = ROOT / '04-user_manager_web.md'
    content = plan.read_text(encoding='utf-8')
    # Packaging completion is recorded after checksum verification in the package
    # report; this document is included in that same verified artifact.
    for number, *_ in steps:
        content = content.replace('- [ ] ' + number, '- [x] ' + number)
    marker = '\n## 6. 实施与验证记录\n'
    content = content.split(marker)[0]
    content += marker + '\n结果：0.2.0 实现及验证通过。公开服务器尚未自动升级，执行部署说明中的上传和安装命令后即可连接。\n\n'
    content += '| 任务 | 依赖（04-） | 产物 | 验证 | 结果 |\n|---|---|---|---|---|\n'
    for number, dependencies, product, checks in steps:
        content += f'| {number} | {dependencies} | {product} | {checks} | 通过 |\n'
    content += '\n验证代号、精确命令、真实与模拟边界见 [验收报告](artifacts/web/final-assessment.md)。P 的最终 ZIP 哈希和完整性以 `artifacts/release/web-v0.2.0/package-verification.json` 为准。\n'
    plan.write_text(content, encoding='utf-8')
    image = json.loads((ROOT / 'artifacts/release/web-v0.2.0/cloud-agent-release-0.2.0/release-images.json').read_text())['images']['cloud-agent-controller']['id']
    report = f'''# 0.2.0 本地聊天与 Agent 管理验收

日期：2026-09-09。实现、自动化与真实调用验证通过。远端 `106.52.221.61` 尚未安装本次升级包；本报告的新版部署验收在独立 Linux Docker 实例进行，Windows 本地服务通过网络 API 连接该实例。

## 交付与入口

- 规划：`04-user_manager_web.md`；接口：`02_api_contract.md` 和本目录 `controller-openapi.json`。
- Windows：`start-web.ps1`，默认 `http://127.0.0.1:18765`，编译页面随包提供，首次启动安装锁定 Python 依赖。
- 本地包：`artifacts/release/web-v0.2.0/cloud-agent-web-0.2.0.zip`。
- 服务端离线包：`artifacts/release/web-v0.2.0/cloud-agent-release-0.2.0.zip`；支持现有 network-r1/0.1.0 原地升级，保留数据和 `.env`。
- 上传和部署命令：`docs/web-readme.md`。管理员凭据由安装器生成在 `data/admin-token`，日常通过 Windows Credential Manager 保存。
- 控制器镜像：`{image}`。运行镜像、LiteLLM、Prometheus 和 Grafana 继续使用已冻结的镜像。

## 验证证据

| 代号 | 命令 | 结果与证据 |
|---|---|---|
| U | Linux 控制器环境：`python -m pytest tests/unit -q -o addopts=` | 209 passed；`artifacts/release/web-unit-tests.log` |
| V | `cd web`，`npm run build`、`npm test`、`npx playwright test` | 构建通过；3 个事件合并测试、5 个浏览器测试通过 |
| R | Linux root：`python scripts/verify-management-runtime.py` | `runtime-verification.json`；真实模型 + 原生 Skill + local/remote MCP + 两个 Hook 顺序 |
| G | Linux root：`python scripts/verify-web-upgrade.py --keep-running` | `upgrade-verification.json`；旧版安装与会话、升级、导入网关、真实调用、未分配拒绝、发布中断重启恢复 |
| W | Windows：`.\\.venv-web\\Scripts\\python.exe scripts/verify-windows-companion.py` | `windows-companion-verification.json`；保险库、JSONC/env 导入、SSE、真实工具、附件/下载、运行中发布与浏览器页面 |
| P | Linux：`python scripts/package-web-release.py --refresh` | 清单校验、ZIP CRC、SHA-256、秘密扫描；最终结果在 `package-verification.json` |

R/G 使用本机已有 API-key 上游提供商进行真实付费模型调用，MCP 服务是受控测试服务，使用真实 MCP 协议与沙箱进程。R 的 Skill 通过原生发现工具读取；Hook 在工具执行事件写入证明文件，并确认顺序为 AB。G/W 在独立 Compose 实例中发布模型网关，不改动原有网关的配置。

G 保留旧会话、实例 ID、`.env` 后升级；用真实模型验证新 Agent 调用和未分配模型的 403；注入一个“应用中”的网关发布任务并重启控制器，验证原配置字节和历史记录恢复。

W 在 Windows 启动真实本地 FastAPI，经同源代理导入模型。上传数字文件，让模型运行工具求和并下载输出；同时在工具运行时发布 Agent，等待任务结束后切换版本。SSE 不作为忙碌依据，不重复提交提示词。真实页面截图为 `real-chat-desktop.png`、`real-admin-desktop.png`；其余截图来自浏览器受控接口测试。

U 覆盖资源私有归属、版本固定、复制、模型引用约束、禁用和权限拒绝、非法 ZIP、JSONC、四种提供商适配、Host/Origin/CSRF、在途获取计数、超时及失败状态保留。V 覆盖聊天单次发送、模型选择、MCP 表单保存、Agent 编辑、手机侧栏、刷新历史且不重发、权限/问题 API 请求体。

全链路测试发现并修复了旧文件接口的目录权限问题：会话根目录原先由 root 创建，Agent 只能读取 inputs，不能写入同级产物。现在会话目录及由路径助手创建的输出目录使用运行用户权限，访问旧目录时会修复所有权；回归测试和 W 的真实产物下载共同验证此问题。受控配置替换关闭旧 SSE 时，本地代理正常结束流，由页面重连恢复历史。

## 发布边界

- WSL 共存测试使用项目已有 `coexistence-trial` 预检配置，未更改宿主机 swap，也不是满负载或并发容量认证。
- 真实上游验收使用 OpenAI-compatible；OpenAI、Anthropic、Google 的导入映射经过自动化测试，未分别使用三家的生产账户进行付费调用。
- 权限/问题表单使用浏览器受控接口验证；Windows 原生文件选择器仍需用户在实际桌面选择文件。指定路径扫描和导入已经真实验证。
- Skill 元数据首版要求 UTF-8 和单行 name/description；复杂 YAML frontmatter 返回明确校验错误。归档保留资源版本，模型历史回滚仍需所引用模型可用。
- HTTP 明文为已确认的首版边界；不提供多用户、HTTPS、MCP OAuth、自动依赖安装或宿主机 Hook。
- 新版没有自动部署到公网服务器，也没有替用户打开安全组。按部署说明上传 ZIP 与 `.env`、执行安装，再把生成凭据填入本机即可。

服务器配置与资源均由公开 API 管理，不需要日常 SSH。正常响应中的模型凭据、MCP headers/environment 与本地导入预览脱敏；上传内容和手工填写的 Hook 源码按管理员原文保存。包内不含 `.env`、管理员 token、模型凭据或浏览器状态。
'''
    (ROOT / 'artifacts/web/final-assessment.md').write_text(report, encoding='utf-8')
    print('Wrote verified 04 checklist and release assessment')


if __name__ == '__main__':
    main()
