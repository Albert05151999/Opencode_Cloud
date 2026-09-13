# Model gateway

`python -m model_gateway.main` starts the authenticated FastAPI control plane and LiteLLM Router data plane. Install the module requirements (LiteLLM 1.98.0). Set `SERVICE_TOKEN`, `DATA_ROOT`, `LOG_ROOT`, and `SERVICE_PORT`, or use the rendered `MODULE_CONFIG` shared service configuration.

Operations submits immutable releases to `/internal/v1/config/validate` and `/activate`: `{release_id, version, configuration, models}`. Configuration uses the existing LiteLLM `model_list` and supported router settings. Activation first constructs a router, then atomically persists mode-0600 state and swaps it; in-flight requests retain their original router. Matching release IDs are idempotent; conflicting content returns 409. `/rollback` with the expected active `release_id` restores one previous release. `/status` reports only version/identity, never credentials.

The service exposes `/v1/models`, `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`, `/v1/responses`, and `/v1/rerank`. Streaming chat responses preserve incremental SSE and close the source when cancelled. Missing initial activation returns readiness 503. All endpoints except `/health/live` require the internal service credential, including model requests; the API gateway enforces external identity and model permissions.

Draft model tests build an isolated in-memory router and never activate it. Secret placeholders can resolve against the currently applied model snapshot. A catalog draft that has not been applied must provide resolved credentials via its service contract. Provider errors are categorized without returning credential-bearing exception text.

The own LiteLLM callback uses the shared structured logging adapter; arbitrary callback module names in compiled inputs are ignored. Unit/contract validation: `python -m pytest test/model_gateway`. Tests use a deterministic router double; real provider and container verification remains an integration deployment check.

沙箱运行时使用单独的 `MODEL_GATEWAY_TOKEN`，仅授权 `/v1/*`，不能激活配置或读取管理接口。Agent 配置使用 `{env:MODEL_GATEWAY_TOKEN}` 引用，sandbox_manager 在创建沙箱时注入运行时环境；上游供应商凭据仅保留在 model_gateway 的已应用配置内。推理链路将有效追踪上下文作为 `traceparent` 传给上游，同时保持原生 SSE。

已在独立 Python 3.12 环境安装真实 LiteLLM 1.98.0，并通过本机模拟 OpenAI 上游验证编译配置参数、激活、增量 SSE、运行时令牌权限隔离和追踪关联；没有调用付费模型。复现：安装 `requirements.lock` 与 pytest，执行 `LITELLM_LOCAL_MODEL_COST_MAP=True python -m pytest test/model_gateway`。
