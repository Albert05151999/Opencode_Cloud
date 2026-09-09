# 会话文件修复包 ui-r3

> 此为旧补丁说明。0.2.1 已实现服务端原生会话目录绑定，请按根目录 `部署指南.md` 升级；不再安装下文的 `session-workspace` Hook。若已安装，请先从 Agent 绑定中移除并发布，以免旧 Hook 重复拼接目录。

## 已修复的 Web 行为

- 会话结束（`session.idle` 或状态变为 `idle`）后，自动刷新已打开的文件面板；SSE 重连后也刷新。SSE 是长期连接，不以连接关闭作为一次回答结束的标志。
- 文件面板提供圆形刷新按钮，保留当前浏览目录；显示准确的绝对路径和 0 字节文件。
- 切换会话关闭旧文件面板，丢弃迟到的列表响应，避免混入另一会话的文件。
- 上传后刷新文件面板，校验服务器返回的文件大小与本机文件大小一致。
- 发送请求前创建当前会话目录，并附带平台返回的完整会话 ID、工作路径和产物目录说明，减少模型拼错路径的情况。

## 更新本地 Web

停止原 Web 终端（Ctrl+C），在本地 PowerShell 执行：

```powershell
$zip = 'E:\Project_Space\Opencode_Cloud\artifacts\release\web-v0.2.0\cloud-agent-web-0.2.0-ui-r3.zip'
$destination = Join-Path $env:LOCALAPPDATA 'OpenCodeCloud'
Expand-Archive -LiteralPath $zip -DestinationPath $destination -Force
Set-Location (Join-Path $destination 'cloud-agent-web-0.2.0')
powershell -ExecutionPolicy Bypass -File .\start-web.ps1
```

已包含 ui-r1、ui-r2 的修复。无需替换服务器镜像。

## 让工具默认使用会话目录

仅提示模型使用某路径不会改变工具的默认 cwd。修复包另附 `docs/session-workspace.mjs`，通过 OpenCode 原生 `tool.execute.before` 设置默认参数，无需修改 OpenCode 或重建镜像。[插件接口说明](https://opencode.ai/docs/plugins/)

通过 Web 管理页完成以下操作：

1. 全局 Hook → 新建，稳定 ID 和名称填写 `session-workspace`，入口选择 `hook.mjs`。
2. 将随包 `docs/session-workspace.mjs` 的完整内容复制到源码框，保存到服务器，然后发布资源。必须通过服务器隔离加载检查。
3. 打开目标 Agent 的配置，绑定该 Hook 已发布版本，保存并发布 Agent。对需要此行为的其他 Agent 分别绑定；全局资源本身不会自动启用。
4. 发布完成后，新发起一次工具调用：让 Agent 不传 workdir 执行 `pwd`，应返回 `/workspace/sessions/<实际会话ID>`。再让它写入相对路径 `outputs/check.txt`，完成后在文件面板查看并下载验证。

Hook 默认处理 bash 的 workdir，read/write/edit 的相对 filePath，以及 glob/grep 的默认 path；创建 inputs、outputs 目录。显式的其他工作目录仍可使用，但明显指向另一会话 ID 的路径会报错，提示使用准确目录。不会修改进程全局 cwd，也不是同一用户各会话之间的安全隔离措施。apply_patch、MCP 和自定义工具仍需要遵循请求中的路径说明，不宣称覆盖所有工具。

Hook 已通过本地参数映射、跨会话路径拼写错误和会话独立性测试；远端固定版本的加载与实际工具执行，以第 2、4 步结果为准。本次没有替你发布远端 Agent 配置。

## 如何理解已有文件

`/workspace` 是 Agent × 用户沙箱的挂载根目录；`sessions/<id>` 是其下的会话文件目录，后者不会因为存在就自动成为进程 cwd。

聊天记录里的上传路径为 `ses_f7b…`，Agent 写转录时用了 `ses_fb…`。这是两个目录：文件面板只列当前会话目录，不按创建者过滤。刷新无法让写在错误目录的文件出现在正确会话下。需要核对真实完整路径后，将已有产物复制回正确会话的 outputs 目录；本次没有自动移动历史文件。

上传文件被读到 0 字节，只能说明远端文件为空。它可能原本就是空文件；没有本机原文件大小或校验值，不能认定内容在上传时丢失。新版检测上传返回大小不一致并报错，合法空文件仍允许上传。
