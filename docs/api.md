# 对外 API 使用手册

适用：OpenCode Cloud 0.3.7，OpenCode 1.18.29。2026-09-16 按源码及运行服务接口结构核对。

这份手册面向自行编写客户端、脚本或第三方系统的使用者。入口、认证、典型完整流程和业务约束在本页；**所有平台接口的路径、Query、Body 字段、必填项、默认值和响应结构见 [完整接口参考](api-reference.md)**。原生 OpenCode 接口也在参考附录中列出。

## 目录

- [1. 地址、认证与公共约定](#1-地址认证与公共约定)
- [2. 第一次调用：创建会话并获取回答](#2-第一次调用创建会话并获取回答)
- [3. SSE、工具权限与中断](#3-sse工具权限与中断)
- [4. 模型和 Agent 管理](#4-模型和-agent-管理)
- [5. MCP、Skill 与 Hook](#5-mcpskill-与-hook)
- [6. 配置导入、导出和模板](#6-配置导入导出和模板)
- [7. 工作区文件](#7-工作区文件)
- [8. 发布任务、沙箱和恢复](#8-发布任务沙箱和恢复)
- [9. 压测](#9-压测)
- [10. 直接调用模型网关](#10-直接调用模型网关)
- [11. 日志与追踪](#11-日志与追踪)
- [12. 错误处理与验证范围](#12-错误处理与验证范围)

## 1. 地址、认证与公共约定

### 入口地址

| 用途 | 地址示例 | 说明 |
| --- | --- | --- |
| 对外 API | `http://服务器IP:18080` | 本文的 `BASE_URL`，端口以部署的 `API_PORT` 为准 |
| 配置了域名和 TLS 的 API | `https://你的域名` | 使用该地址作为 `BASE_URL` |
| 本机管理 Web | `http://127.0.0.1:18765` | 供浏览器使用，不是远程 API 地址 |

路径直接拼接到 `BASE_URL`。例如创建会话是 `/session`，不是 `/cloud/session`，也不是 `/remote/session`。`/remote/*`、`/local/*` 是本地 Web 的代理和本机接口，不属于本文对外 API。`/internal/*` 不对外开放。

### 请求 Header

| Header | 何时需要 | 值 |
| --- | --- | --- |
| `Authorization` | 除 `GET /cloud/health`、`GET /health/live` 外的调用 | `Bearer <ADMIN_TOKEN>`，取服务器发布目录 `.env` 中的值 |
| `Content-Type` | JSON Body | `application/json`；上传文件让客户端自动生成 multipart boundary |
| `X-Cloud-Agent-ID` | 创建会话、订阅事件和其他尚未绑定会话的原生调用 | 已发布且启用的 Agent ID，如 `agent-code` |
| `X-Cloud-Username` | 同上 | 业务用户标识，如 `api-demo`；相同 Agent/用户通常复用沙箱 |
| `X-Cloud-Session-ID` | 权限/问题等 URL 不含会话 ID 的会话相关接口 | 本次会话返回的 `ses_...` |
| `Accept` | SSE | `text/event-stream` |
| `X-Cloud-Request-ID` | 可选日志关联 | 1–128 位字母、数字、`_`、`.`、`:`、`-` |
| `traceparent` | 可选分布式追踪 | W3C 格式，如 `00-32位十六进制traceid-16位spanid-01`，ID 不得全零 |

会话 URL 已携带 session ID 时可以由服务端解析归属；客户端仍可统一携带 Agent/用户名，但必须与会话归属一致。这些路由 Header **不是用户认证或权限隔离凭据**，不得把管理员令牌直接发给不受信任的终端用户。业务系统应在自己的后端保管令牌并验证用户身份。

原生 JSON 请求也支持顶层 `_cloud` 路由元数据，例如创建会话时传 `{"title":"示例","_cloud":{"agent_id":"agent-code","username":"api-demo"}}`，服务端转发前会移除 `_cloud`。可选 `session_workspace` 指定受工作区边界约束的会话目录；通常省略，使用平台分配路径。不要在 Body 和 Header 中填写不同的归属信息。

`SERVICE_TOKEN` 用于内部服务，`MODEL_GATEWAY_TOKEN` 用于沙箱内部推理，外部统一入口使用 `ADMIN_TOKEN`。第三方供应商 Key 配置在模型中，不能作为平台登录令牌。

### Body、版本与响应

- JSON 字段名区分大小写。管理接口大多拒绝未定义字段。
- 稳定资源 ID 使用字母/数字开头，其余为字母、数字、`_` 或 `-`，最多 64 位。
- `revision` 是全局 Catalog 乐观锁版本，从 `GET /cloud/admin/catalog` 读取。多人编辑时带上它；收到 409 后刷新并核对，不要盲目覆盖。
- 保存草稿、发布资源版本、发布 Agent/模型网关是不同动作。收到 `{"ok":true}` 或 `job_id` 不代表运行配置已生效。
- 分页列表通常为 `{"items":[],"total":0}`；`/cloud/agents`、`/cloud/models` 等直接返回数组，不能假定所有接口都有统一 `data` 包装。
- 运维请求中的 Body `request_id` 用于幂等，与日志 Header `X-Cloud-Request-ID` 不同。同一次操作重试复用原 ID 和原参数，新操作生成新 ID；并非所有写接口都支持幂等。

## 2. 第一次调用：创建会话并获取回答

前提：模型网关已发布，Agent 已发布且启用。用 `GET /cloud/agents` 检查 `enabled`、`version` 和 `allowed_model_ids`；未启用、未发布或归档的 Agent 不可用于新生成。

### Bash / curl

下列代码在 Bash 中执行；JSON 解析需要 `python3`。把 Token 放到当前 shell 的 `ADMIN_TOKEN` 环境变量中。

```bash
export BASE_URL='http://服务器IP:18080'
export ADMIN_TOKEN='替换为服务器ADMIN_TOKEN'
export AGENT_ID='agent-code'
export USERNAME='api-demo'

curl -fsS "$BASE_URL/cloud/health"
curl -fsS -H "Authorization: Bearer $ADMIN_TOKEN" "$BASE_URL/cloud/health/ready"
curl -fsS -H "Authorization: Bearer $ADMIN_TOKEN" "$BASE_URL/cloud/agents"
curl -fsS -G -H "Authorization: Bearer $ADMIN_TOKEN" \
  --data-urlencode "agent_id=$AGENT_ID" "$BASE_URL/cloud/models"

SESSION_ID=$(curl -fsS -X POST "$BASE_URL/session" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-Cloud-Agent-ID: $AGENT_ID" -H "X-Cloud-Username: $USERNAME" \
  -H 'Content-Type: application/json' \
  --data '{"title":"API 入门会话"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -fsS -X POST "$BASE_URL/session/$SESSION_ID/message" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-Cloud-Agent-ID: $AGENT_ID" -H "X-Cloud-Username: $USERNAME" \
  -H 'Content-Type: application/json' \
  --data '{"parts":[{"type":"text","text":"你好，请简短介绍你能做什么。"}]}'
```

创建会话返回对象，其中 `id` 为会话 ID。同步发送消息返回包含 `info`、`parts` 的消息对象；正文位于 `parts` 中 `type="text"` 的元素，工具调用和推理是其他 part 类型。不要只取数组第一项。同步生成可能较慢，长任务推荐下一节的异步接口。

示例省略 `model`，使用 Agent 已发布的默认模型。如需指定，Body 增加：

```json
{"model":{"providerID":"cloud-model-gateway","modelID":"glm"},"parts":[{"type":"text","text":"你好"}]}
```

`modelID` 必须在该 Agent 的 `allowed_model_ids` 中；全局存在该模型并不等于 Agent 可以使用它。`glm`、`minimax` 是可配置的别名，不保证每个部署都有这两个名字。

### Windows PowerShell

此示例不需要 `sh` 或 Bash。使用 `Invoke-RestMethod`，中文 Body 显式编码为 UTF-8。粘贴到 PowerShell 可直接执行；如果保存为 `.ps1` 并用 Windows PowerShell 5.1 运行，文件需保存为 UTF-8 BOM，避免中文被按系统编码误读。

```powershell
$baseUrl = 'http://服务器IP:18080'
$env:ADMIN_TOKEN = '替换为服务器ADMIN_TOKEN'
$headers = @{
    Authorization = "Bearer $env:ADMIN_TOKEN"
    'X-Cloud-Agent-ID' = 'agent-code'
    'X-Cloud-Username' = 'api-demo'
}
Invoke-RestMethod "$baseUrl/cloud/health"
Invoke-RestMethod "$baseUrl/cloud/agents" -Headers $headers
$sessionBody = [Text.Encoding]::UTF8.GetBytes('{"title":"API 入门会话"}')
$session = Invoke-RestMethod "$baseUrl/session" -Method Post -Headers $headers `
    -ContentType 'application/json; charset=utf-8' -Body $sessionBody
$messageBody = @{ parts = @(@{type='text'; text='你好，请简短介绍你能做什么。'}) } | ConvertTo-Json -Depth 10
$answer = Invoke-RestMethod "$baseUrl/session/$($session.id)/message" -Method Post `
    -Headers $headers -ContentType 'application/json; charset=utf-8' `
    -Body ([Text.Encoding]::UTF8.GetBytes($messageBody))
$answer.parts | Where-Object type -eq 'text' | Select-Object -ExpandProperty text
```

本页之后的 curl 示例采用 Bash 换行语法，不能直接粘贴到 PowerShell。Windows 可使用上面的请求模式：URL 和 JSON 不变，Header 放入 `$headers`，上传使用 `curl.exe` 或支持 multipart 的 HTTP 客户端。

## 3. SSE、工具权限与中断

### 推荐流程

1. `POST /session` 获取 session ID。
2. `GET /event`，带相同 Agent、用户名以及 `Accept: text/event-stream`，保持连接。
3. 收到 `server.connected` 后，再 `POST /session/{sessionID}/prompt_async`。
4. 消费事件并按 session ID 过滤；该沙箱的流可能包含其他会话。
5. 收到目标会话的完成/空闲事件后，通过 `GET /session/{sessionID}/message` 校准最终消息。

终端 A 订阅（使用第 2 节的环境变量）：

```bash
curl -N -f "$BASE_URL/event" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-Cloud-Agent-ID: $AGENT_ID" -H "X-Cloud-Username: $USERNAME" \
  -H 'Accept: text/event-stream'
```

终端 B 在订阅就绪后发送（设置实际 `SESSION_ID`）：

```bash
curl -i -X POST "$BASE_URL/session/$SESSION_ID/prompt_async" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-Cloud-Agent-ID: $AGENT_ID" -H "X-Cloud-Username: $USERNAME" \
  -H 'Content-Type: application/json' \
  --data '{"parts":[{"type":"text","text":"你好，请简短回答。"}]}'
```

`prompt_async` 成功通常返回 **204 空 Body**，不是最终回答。可选 `messageID` 由客户端生成，如 `msg_` 加 32 位十六进制；请求超时不能据此认定服务端未接收。

SSE 每帧由空行分隔，`data:` 是 JSON。例如：

```text
data: {"type":"server.connected","properties":{}}

data: {"type":"session.idle","properties":{"sessionID":"ses_实际会话ID"}}

```

处理 `message.updated`、`message.part.updated`、`message.part.delta`、`session.status`、`session.idle`、`session.error`。session ID 可能位于 `properties.sessionID`、`properties.info.sessionID` 或 `properties.part.sessionID`。增量与快照按 message/part ID 合并，避免重复拼接；工具 part 的状态与输出不要当成普通文本增量。

断线后重新订阅并读取历史消息，不要自动重新提交 prompt。关闭 SSE 仅停止接收；中断生成需 `POST /session/{sessionID}/abort`（无 Body）。

仓库提供终端实现 [sse_chat.py](../api_gateway/tools/sse_chat.py)，执行时显式指定模型，避免依赖脚本中的默认模型名：

```bash
export CLOUD_AGENT_ADMIN_TOKEN="$ADMIN_TOKEN"
python api_gateway/tools/sse_chat.py --base-url "$BASE_URL" \
  --agent "$AGENT_ID" --username "$USERNAME" --model glm --prompt '请简短回答你好'
```

### 权限和问题

工具执行可能等待用户批准或回答。先读取 `/permission`、`/question` 或相应 SSE 事件，取得实际 request ID。以下接口带路由 Header，并增加 `X-Cloud-Session-ID: <SESSION_ID>`：

| 操作 | 方法与 URL | JSON Body |
| --- | --- | --- |
| 回复权限 | `POST /permission/{requestID}/reply` | `{"reply":"once"}`；枚举 `once`、`always`、`reject` |
| 回答问题 | `POST /question/{requestID}/reply` | `{"answers":[["选项文字"]]}`；每个问题对应一个答案数组 |
| 拒绝问题 | `POST /question/{requestID}/reject` | 无 |
| 中断生成 | `POST /session/{sessionID}/abort` | 无 |

会话重命名用 `PATCH /session/{sessionID}`，如 `{"title":"新标题"}`；删除用 `DELETE /session/{sessionID}`。历史列表和消息分页的完整参数见参考附录。

平台管理的 provider、MCP 和配置不能绕过管理 API 通过原生 `PATCH /config`、`PUT /auth/*` 或 `/mcp/*` 写入；可能返回 403，即使上游 OpenCode schema 存在该接口。

## 4. 模型和 Agent 管理

### 标准发布顺序

读取 Catalog → 保存模型 → 发布模型网关 → 等待任务成功 → 保存 Agent → 发布 Agent → 等待任务成功 → 创建会话。

`GET /cloud/admin/catalog?compact=true` 返回 `revision`、`models`、`agents`、`resources`、`jobs` 等。`compact` 用于列表读取，完整历史使用不带 `compact=true` 的请求。

### 保存模型和多账户池

`PUT /cloud/admin/models/glm`，Body 为 `ModelWrite`：

```json
{
  "model": {
    "id": "glm",
    "name": "GLM",
    "provider": "openai-compatible",
    "upstream_model": "替换为供应商模型ID",
    "base_url": "https://供应商地址/v1",
    "enabled": true,
    "deployments": [
      {"id":"account-1","api_key":"替换为账户一Key","enabled":true},
      {"id":"account-2","api_key":"替换为账户二Key","enabled":true}
    ]
  }
}
```

可在顶层加入读取到的 `revision`。单账户可以使用 `model.api_key`；多账户使用 `deployments`。账户可独立配置 `base_url`、`upstream_model`、`headers`、`rpm`、`tpm`、`weight`。多个账户映射为同一个全局模型名，Agent 只选 `glm`。真实提供商地址和模型 ID 参见 [模型配置](model-configuration.md)。

把 JSON 保存为 UTF-8 的 `model.json` 后调用：

```bash
curl -fsS -X PUT "$BASE_URL/cloud/admin/models/glm" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  --data-binary @model.json
curl -fsS -X POST "$BASE_URL/cloud/admin/models/glm/test" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
curl -fsS -X POST "$BASE_URL/cloud/admin/models/apply" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  --data '{"request_id":"publish-models-demo-0001"}'
```

保存返回 `{"ok":true}`；测试可能 HTTP 200 但 `ok:false`，必须检查业务结果；发布返回 `{"job_id":"..."}`，按第 8 节等待。

其他模型接口：`GET /cloud/admin/models`、`POST /cloud/admin/models/import`（`models` 数组，`replace` 默认 false）、`POST /cloud/admin/models/test-draft`（同 `ModelWrite`）、`POST /cloud/admin/models/config-preview`（同 `ModelWrite`）、`GET /cloud/admin/provider-templates`、`DELETE /cloud/admin/models/{model_id}?revision=...`。被 Agent 引用的模型不能直接删除或停用。读取时凭据会脱敏，不要把脱敏字符串当成新的 Key。

### 保存 Agent 与资源限制

`PUT /cloud/admin/agents/my-agent`：

```json
{
  "config": {
    "name": "我的 Agent",
    "description": "通过 API 配置",
    "enabled": true,
    "instructions": "你是一个有帮助的助手。",
    "allowed_model_ids": ["glm"],
    "default_model_id": "glm",
    "small_model_id": null,
    "cpu_limit": 2,
    "memory_mb": 2048,
    "bindings": []
  }
}
```

`cpu_limit` 为整数 1/2/4/8，`memory_mb` 为 1024/2048/4096/8192（MiB），各自省略或为 null 时继承服务器默认值。限制作用于每个沙箱，不是整个 Agent 所有用户总和。工作目录映射到宿主机，没有 Agent 级容器磁盘容量字段；上传仍受文件服务规则约束。

保存返回 `{"ok":true}`。随后 `POST /cloud/admin/agents/my-agent/apply`，Body 如 `{"request_id":"publish-agent-demo-0001"}`，等待 `job_id` 成功。发布会切换版本并按流程重建受影响的沙箱，保留映射工作目录。

| 操作 | URL | Body / Query |
| --- | --- | --- |
| 列出管理记录 | `GET /cloud/admin/agents` | 无 |
| 复制草稿 | `POST /cloud/admin/agents/{agent_id}/copy` | `{"id":"new-agent"}`，可带 revision；新 Agent 仍需发布 |
| 更新模型和绑定 | `PUT /cloud/admin/agents/{agent_id}/bindings` | `bindings`、`allowed_model_ids`、`default_model_id`、`small_model_id`、`revision` 按需传入 |
| 预览未保存配置 | `POST /cloud/admin/agents/{agent_id}/config-preview` | 同 AgentWrite；返回 `opencode`、`sources`、`resources` |
| 生效配置与草稿 | `GET /cloud/admin/agents/{agent_id}/effective-config` | 无 |
| 全局配置预览 | `GET /cloud/admin/config-preview` | 无 |
| 回滚 | `POST /cloud/admin/agents/{aid}/rollback` | `{"version":1,"request_id":"rollback-demo-0001"}` |

## 5. MCP、Skill 与 Hook

扩展资源必须先发布获得固定版本，再绑定到 Agent 并发布 Agent。

创建远程 MCP：`PUT /cloud/admin/resources/search-mcp`：

```json
{"resource":{"kind":"mcp","name":"search-mcp","owner":null,"data":{"type":"remote","url":"https://你的MCP服务/mcp","headers":{}}}}
```

`owner:null` 为全局资源；指定 Agent ID 为该 Agent 私有资源。MCP 支持 local/remote 配置，OAuth 不由平台自动配置；local 命令不会自动安装依赖。创建 Hook 使用同一接口，`kind:"hook"`，`data` 包含 `entry` 和 `sources`，如 `{"entry":"plugin.mjs","sources":{"plugin.mjs":"此处填写实际插件源码"}}`。这不是可直接运行的示例插件，源码须符合 OpenCode 插件接口并通过编译探测。

Skill 用上传接口（支持 `SKILL.md` 或符合平台目录规则的 ZIP）：

```bash
curl -fsS -X POST "$BASE_URL/cloud/admin/resources/my-skill/upload" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -F 'file=@SKILL.md'
curl -fsS -X POST "$BASE_URL/cloud/admin/resources/my-skill/publish" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' --data '{}'
```

上传表单可带 `owner`、`revision`；上传上限 20 MiB。发布返回 `{"version":1}`，然后在 Agent 的 `bindings` 中加入 `{"id":"my-skill","version":1}`，保存并发布 Agent。Hook 发布/扩展测试需要可用的目标 Agent，Body 为 `{"agent_id":"my-agent"}`。

资源查询、版本、文件、复制和测试的完整参数见参考中的 `/cloud/admin/resources/*`。

| 生命周期操作 | URL | Body / Query |
| --- | --- | --- |
| 归档资源 | `POST /cloud/admin/resources/{resource_id}/archive` | `{}`，可带 `revision` |
| 恢复资源 | `POST /cloud/admin/resources/{resource_id}/restore` | `{}`，可带 `revision` |
| 永久删除资源 | `DELETE /cloud/admin/resources/{resource_id}` | 可选 Query `revision` |

这三个接口适用于 MCP、Skill、Hook，成功返回 `{"ok":true}`。删除前必须归档；Agent 草稿、历史发布版本或模板仍引用该资源时返回 409，不能直接删除。归档不会破坏已经绑定的固定版本。管理页默认隐藏归档资源，打开“显示已归档和删除中的资源”后可恢复或删除；删除中表示该删除请求正在执行。

## 6. 配置导入、导出和模板

| 操作 | 方法与 URL | 请求 |
| --- | --- | --- |
| 普通导出（脱敏） | `GET /cloud/admin/exports/resources` | 无；响应为 JSON 下载 |
| 加密导出 | `POST /cloud/admin/exports/encrypted` | `{"password":"replace-with-strong-passphrase","include_credentials":true}`；换成自选至少 12 字符口令 |
| 原生 OpenCode 导出 | `GET /cloud/admin/exports/native/{aid}` | 无；响应为 ZIP |
| 导入预览 | `POST /cloud/admin/imports/preview` | multipart：`file`，加密包另填 `password` |
| 提交导入 | `POST /cloud/admin/imports/{preview_id}/commit` | `{"selections":[{"key":"预览返回的key","target_id":"目标ID","replace":false}]}` |
| 模板列表 | `GET /cloud/admin/agent-templates` | 无 |
| 从模板恢复 Agent | `POST /cloud/admin/agent-templates/{tid}/restore` | `{"agent_id":"new-agent","models":{},"resources":{}}` |

```bash
curl -fsS -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$BASE_URL/cloud/admin/exports/resources" -o cloud-resources.json
curl -fsS -X POST "$BASE_URL/cloud/admin/imports/preview" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -F 'file=@cloud-resources.json'
```

必须检查预览，再用返回的 `preview_id` 和各条 `key` 提交。`models` 映射源模型 ID 到目标模型 ID；模板的 `resources` 映射源资源 ID 到 `{"id":"目标资源ID","version":1}`。恢复返回 `{"agent_id":"new-agent","published":false}`；导入和恢复不等于发布。普通导出不含真实 Key，导入后可能需要补齐凭据并启用模型。详见 [导入导出指南](import-export.md)。

## 7. 工作区文件

文件接口的归属来自 Query/Form 的 `agent_id`、`username`、`session_id`，不是只靠路由 Header。涉及会话工作区时传入对应 `session_id`。

```bash
curl -fsS -X POST "$BASE_URL/cloud/files/upload" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -F "agent_id=$AGENT_ID" -F "username=$USERNAME" -F "session_id=$SESSION_ID" \
  -F 'file=@report.txt' -F 'relative_path=report.txt'

curl -fsS -G "$BASE_URL/cloud/files/list" -H "Authorization: Bearer $ADMIN_TOKEN" \
  --data-urlencode "agent_id=$AGENT_ID" --data-urlencode "username=$USERNAME" \
  --data-urlencode "session_id=$SESSION_ID" --data-urlencode 'path=.'

curl -fsS -G "$BASE_URL/cloud/files/download" -H "Authorization: Bearer $ADMIN_TOKEN" \
  --data-urlencode "agent_id=$AGENT_ID" --data-urlencode "username=$USERNAME" \
  --data-urlencode "session_id=$SESSION_ID" --data-urlencode 'path=report.txt' -o downloaded-report.txt
```

列表返回 `{"entries":[...]}`；下载是二进制响应，不能按 JSON 解析。路径受工作区边界校验，不支持用 `..` 或宿主机绝对路径越界。上传大小及用户工作区配额按部署配置执行。

## 8. 发布任务、沙箱和恢复

### 等待异步结果

```bash
# JOB_ID 使用提交返回值；不要将示例字符串当作真实 ID。
curl -fsS -H "Authorization: Bearer $ADMIN_TOKEN" "$BASE_URL/cloud/admin/jobs/$JOB_ID"
```

任务常见字段为 `id`、`kind`、`target`、`status`、`checkpoint`、`error`、`result`、`created`、`updated`。`queued`、`running`、`waiting` 以及验证/应用中的状态不是完成；`succeeded` 才表示任务成功，`failed`、`cancelled`、`interrupted`、`needs_recovery` 不能显示成成功。发布成功后再核对 Catalog 的 `active` / `gateway_active` 与任务版本。超时先查询任务和目标状态，避免重复发起。

| 操作 | 方法与 URL | Body / Query |
| --- | --- | --- |
| 任务列表 | `GET /cloud/admin/jobs` | `offset=0`、`limit=25`（1–100）、可选 `target` |
| 下载完整任务记录 | `GET /cloud/admin/jobs/export` | 无；JSON 数组，含服务器保留的全部记录，排除内部请求载荷 |
| 取消任务 | `POST /cloud/admin/jobs/{jid}/cancel` | 无；部分阶段和删除任务不可取消 |
| 不确定结果对账 | `POST /cloud/admin/jobs/{jid}/reconcile` | `{"request_id":"reconcile-demo-0001"}` |
| 重试删除 | `POST /cloud/admin/jobs/{jid}/retry` | `request_id`、新的 `preview_id`、`confirmation`（Agent ID）；不是通用任务重试 |
| 沙箱列表 | `GET /cloud/admin/sandboxes` | `q`、`status`、`offset=0`、`limit=50`（1–100） |
| 沙箱详情 | `GET /cloud/admin/sandboxes/{sid}` | 无 |
| 启动 | `POST /cloud/admin/sandboxes/{sid}/start` | `{"request_id":"start-demo-0001"}` |
| 停止/重启 | `POST /cloud/admin/sandboxes/{sid}/stop` 或 `/restart` | `{"request_id":"restart-demo-0001"}` |
| 销毁容器 | `POST /cloud/admin/sandboxes/{sid}/destroy` | `{"request_id":"destroy-demo-0001"}`；保留会话与映射工作区，下次调用重建 |
| 强制操作预览 | `GET /cloud/admin/sandboxes/{sid}/force-preview` | 无 |
| 归档/恢复 Agent | `POST /cloud/admin/agents/{aid}/archive` 或 `/restore` | `{"request_id":"archive-demo-0001"}` |
| 删除未发布空 Agent | `POST /cloud/admin/agents/{aid}/delete-empty` | `{"request_id":"delete-empty-demo-0001"}`，受状态/引用检查 |
| 删除影响预览 | `GET /cloud/admin/agents/{aid}/delete-preview` | 无 |
| 永久删除 | `POST /cloud/admin/agents/{aid}/delete` | `request_id`、`preview_id`、`confirmation`（精确 Agent ID） |
| 恢复策略 | `GET` / `PUT /cloud/admin/recovery-policy` | PUT 为 RecoveryPolicy，完整字段见参考 |
| 安全运行状态 | `GET /cloud/operations/security-status` | 无 |

`request_id` 长度 8–128。强制停止/重启/销毁需要先查看预览，提交 `force_preview_id` 以及精确沙箱 ID 的 `confirmation`。运行中或状态无法确认的沙箱不能普通销毁，强制操作会中断当前执行。销毁完成后状态为 `destroyed`，不会立即自动重建；同一 Agent/用户下次访问会话时按需重建并读取保留的数据。删除 Agent 要先归档并核对影响；删除预览有效期 300 秒，内容变化需重新预览。永久删除涉及关联数据，不等价于归档。

管理页的发布记录展示最近 50 条，进入页面时刷新一次，也可手动刷新；不定时轮询。下载按钮获取完整保留记录，不受 50 条显示限制。

## 9. 压测

先 `GET /cloud/admin/load-tests/options` 取得可选的已发布 Agent，再 `GET /cloud/admin/load-tests/capacity` 获取容量。`known`、`admission_allowed` 必须为 true，且请求的总 CPU/内存不超过 `remaining_cpu`、`remaining_memory_mb`。

`POST /cloud/admin/load-tests`：

```json
{
  "request_id":"load-test-demo-0001",
  "agents":[{"agent_id":"agent-code","users":1,"cpu_limit":1,"memory_mb":1024}],
  "timeout_seconds":180,
  "prepare_timeout_seconds":120
}
```

返回 HTTP 202，Body 为 `{"id":"实际压测ID","created":true}`，使用返回的 `id` 查询完整记录。每个 Agent 只能出现一次，总用户数不超过 100。压测使用独立测试用户/沙箱及固定工作负载，不接受任意 prompt。这里的 CPU 可为 0.25–64，内存 256–65536 MiB；**压测参数范围不同于普通 Agent 编辑器的固定档位**。

| 方法与 URL | 参数 / 返回 |
| --- | --- |
| `GET /cloud/admin/load-tests` | `offset`、`limit`，返回分页记录 |
| `GET /cloud/admin/load-tests/{rid}` | 状态、用户阶段、统计和失败信息 |
| `POST /cloud/admin/load-tests/{rid}/cancel` | 无 Body；HTTP 202 |
| `POST /cloud/admin/load-tests/{rid}/cleanup` | `{"confirmation":"实际压测ID"}`；HTTP 202，清理测试数据前确认范围 |
| `GET /cloud/admin/load-tests/{rid}/report?format=json` | JSON 下载；`format=csv` 下载 CSV |

容量按全机容器配额、系统预留和实际可用内存计算，包含其他项目与可重启沙箱。CPU 实时使用率低不代表还有可分配配额；压测会额外创建沙箱。不要靠重复点击绕过 409。

## 10. 直接调用模型网关

如果只需要推理，不需要 Agent 工具和工作区，可以调用 `/llm/v1/*`，仍使用外部 `ADMIN_TOKEN`。

```bash
curl -fsS "$BASE_URL/llm/v1/models" -H "Authorization: Bearer $ADMIN_TOKEN"
curl -fsS -X POST "$BASE_URL/llm/v1/chat/completions" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  --data '{"model":"glm","messages":[{"role":"user","content":"你好"}],"stream":false}'
```

返回 OpenAI 兼容的 completion 对象。`stream:true` 时使用 SSE，每帧为 `data: <JSON>`，结束为 `data: [DONE]`；与 Agent `/event` 的事件类型不同。

支持的 POST 路径：`/llm/v1/chat/completions`、`/llm/v1/completions`、`/llm/v1/embeddings`、`/llm/v1/responses`、`/llm/v1/rerank`。分别使用 `messages`、`prompt`、`input`、`input`、`query`/`documents` 等相应 API 字段和 `model`。路由存在不代表当前供应商模型支持该能力；本部署的聊天模型不保证支持 embedding、rerank 或 Responses。请求体透传至 LiteLLM，不是 AgentDefinition；没有创建 Agent 会话，也不会执行 Agent 工具。

## 11. 日志与追踪

- `GET /cloud/logs/modules`：可查询模块与实例。
- `GET /cloud/logs`：支持 `module`、`trace_id`、`session_id`、`job_id`、`limit`。当前接口不接受等级、时间区间或 request_id 过滤参数；可在返回结果中进一步筛选。
- `GET /cloud/logs/export`：下载 JSONL 日志，支持 `module`、`trace_id`、`session_id`、`job_id`，多个条件同时满足。省略条件则导出所有模块现存日志，包括保留的轮转文件，不受预览条数限制。
- `GET /cloud/traces`：查找调用链；`session_only=true` 仅返回包含会话标识的调用链，可与其他筛选条件组合。
- `GET /cloud/traces/{trace_id}`：查看某条调用链。
- `GET /cloud/traces/sessions/{session_id}?limit=50`：会话运行时间线，默认返回最近 50 个执行轮次（上限 200），按开始时间正序展示。`items` 中每轮包含 `runtime`（整轮区间，未记录时 null）、`requests`（平台接入请求）、`phases`（内部模型请求与工具执行）、`trace_ids`、`runtime_observed`、`model_calls`、`observed_duration_ms`；模型阶段的 `children` 包含已记录的分段计时。

会话时间线依据明确的 Trace ID / Message ID 关联记录，隐藏 GET 轮询及文件查询；同一轮可有多次模型调用和工具执行。`runtime_observed:false` 表示未采集到完整的整轮起止，可能来自旧日志或执行尚未闭合，不能当作运行时没有执行。`observed_duration_ms` 是已记录阶段的覆盖范围，不是各阶段耗时之和，也不保证覆盖未记录的执行。结果受日志保留期和扫描上限限制，检查 `partial`、`truncated`、`coverage`。

计时边界：

| 项目 | 实际含义 |
| --- | --- |
| Agent 整轮执行 | OpenCode 用户消息的 `time.created` 到最终助手消息的 `time.completed`；跳过 `tool-calls` 中间消息，包含模型等待、工具执行及 OpenCode 处理，不包含浏览器最后渲染时间 |
| 模型请求全程 | 模型代理接收请求至响应传输结束；包含上游生成与网络等待，**不是网关自身开销** |
| `gateway_prepare` | 网关处理器内解析请求、整理路由参数及请求头的本地准备时间；不是网关全部自身开销 |
| `model_sdk_wait` | 调用 LiteLLM 至 SDK 返回流对象；可能包含路由、重试、供应商等待，不能解释成纯路由或精确 HTTP 200 延迟 |
| `model_response_wait` | 非流式调用至完整响应返回，或调用失败前的等待 |
| `model_first_chunk_wait` | SDK 返回流对象后，到取出第一个流片段的等待；片段可能仅为元数据，不等于首个文本 token |
| `model_stream_transfer` | 首片段之后至上游流迭代结束；包含模型生成、网络、序列化和下游背压 |

供应商内部的排队与纯计算时间目前无法独立测量，不将代理全程冒充供应商纯计算。运行时整轮跨度需要新版运行时镜像和重新发布后的系统追踪插件；旧日志不会补造时长。页面的模块按钮仅按记录来源筛选，不代表从左到右的执行顺序；API `summary.module_duration_ms` 仍为该模块跨度的观测区间并集，包含等待，不能当作模块自身 CPU 开销。

所有准确 Query 名称、枚举和分页边界见 [完整参考](api-reference.md)。例如：

```bash
curl -fsS -G "$BASE_URL/cloud/logs" -H "Authorization: Bearer $ADMIN_TOKEN" \
  --data-urlencode 'module=api_gateway' --data-urlencode 'limit=20'

# 下载某次会话在指定模块中的日志。
curl -fsS -G "$BASE_URL/cloud/logs/export" -H "Authorization: Bearer $ADMIN_TOKEN" \
  --data-urlencode 'module=api_gateway' --data-urlencode "session_id=$SESSION_ID" \
  -o session-logs.jsonl
```

浏览器 F12 → Network → 选择请求 → Response Headers 查看 `X-Cloud-Trace-ID`，复制到调用链页查询；`traceparent` 中包含相同的 Trace ID。本地 Web 的 `/remote/*` 代理响应也保留这些头。瀑布图默认只显示顶层调用，点击父调用逐层展开子调用。横轴保留真实时间；总耗时包含等待子调用的时间，父子嵌套与并发都可能重叠，不应强行首尾相接。

在管理页选择“会话运行时间线”并输入 `session_id`，或点击最近请求中的“会话时间线”，即可查看连续多轮执行；点击阶段的“查看调用链”下钻，再用“返回会话时间线”返回。只有 Session ID 的深链接 `/admin?tab=logs&session=...` 默认打开会话视图。

管理页的“模块日志”提供原始 JSONL 预览与筛选下载。预览和调用链扫描有范围及数量上限；下载覆盖服务器当前保留文件，不包含已经清理的历史，且不是冻结快照。没有查到记录不能证明请求未执行。调用链可能截断或缺少 span，排障时同时保存响应状态、请求 ID、任务 ID 和时间。

## 12. 错误处理与验证范围

| HTTP 状态 | 常见原因 | 客户端处理 |
| --- | --- | --- |
| 400 / 422 | 字段、枚举、路径、引用关系不合法 | 显示 `detail`；422 的 detail 可能是带 `loc`、`msg` 的数组 |
| 401 | ADMIN_TOKEN 缺失/错误或服务端未配置 | 核对服务器实际运行的凭据 |
| 403 | 跨归属访问、模型未授权、原生写配置被禁止 | 核对 Agent/用户/会话归属，改用管理 API |
| 404 | ID 不存在、路径不开放 | 核对路径、部署版本和资源 ID |
| 409 | revision 冲突、操作进行中、容量不足、预览过期 | 刷新并核对，保留用户输入，不盲目重试 |
| 413 | 请求/上传超限 | 减少内容，核对部署限制 |
| 429 | 上游或平台限流 | 按限流信息退避，避免并发重试放大负载 |
| 502 / 503 / 504 | 服务、模型或沙箱尚未就绪/不可用 | 查 readiness、任务和日志；写请求结果未知时先查询 |

模型推理错误可能为 `{"error":{"message":"Model request failed","type":"..."}}`；普通接口通常为 `{"detail":"..."}`。测试接口还可能 HTTP 200 且 `ok:false`。不应仅凭 HTTP 200 判定所有业务操作成功。

### 文档与接口结构来源

- [完整参考](api-reference.md)：当前平台对外路由的字段级附录，以及原生 OpenCode 路由索引。
- `GET /doc`：固定 OpenCode schema 加平台路由扩展，需管理员认证；不包括完整平台管理接口，也不代表所有上游写操作均获平台允许。
- `GET /openapi.json`：网关自身的 FastAPI 描述，代理转发的全部业务接口不会自动合并在其中。
- [原生 OpenCode schema](../api_gateway/resources/upstream/opencode-1.18.29-openapi.json)：原生请求及响应的完整类型定义。

2026-09-16 验证记录：

- 平台业务操作全部纳入字段参考；另列网关/模型推理入口及 188 项原生协议操作，明确原生接口兼容边界。
- JSON 代码块解析、对应 ModelWrite/AgentWrite/LoadRequest/原生消息输入校验通过；Bash 示例语法检查、文档链接检查通过。
- Windows PowerShell 实际调用 10 个读取入口，认证和响应正常；创建临时会话并发送中文请求，收到 `API-DOC-OK`。
- 实际执行 SSE 订阅 → 异步提交 → 接收完成事件，收到 `API-DOC-STREAM-OK`。两个验证会话均已删除，已有会话未修改。
- 0.3.4 实际验证 Trace ID 响应头、三类资源归档/恢复/删除、完整任务下载、按模块和会话下载日志；销毁真实沙箱后重新访问，容器 ID 改变，原有消息和上传文件保留。临时验证 Agent 及其数据已清理。

接口结构从运行服务读取，并与网关分发和源码 DTO 核对。永久删除、强制操作、供应商所有推理能力等没有为了写文档而在用户数据上执行，不宣称全部接口都做过破坏性实测。
