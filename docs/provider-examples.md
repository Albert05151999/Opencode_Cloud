# 七个厂商的配置示例

原生 JSON 示例位于 `examples/providers/`。它们是格式示例，不包含凭据；先在启动本地 Web 的 PowerShell 中设置相应环境变量，再用本机配置路径导入。也可直接在模型表单选模板并填写 API key。

| 文件 / 模板 | 上游模型 ID 示例 | 本机环境变量 | LiteLLM model 前缀 |
|---|---|---|---|
| openai.json | gpt-4.1 | OPENAI_API_KEY | openai/ |
| anthropic.json | claude-sonnet-5 | ANTHROPIC_API_KEY | anthropic/ |
| google.json | gemini-2.5-pro | GOOGLE_API_KEY | gemini/ |
| deepseek.json | deepseek-v4-flash | DEEPSEEK_API_KEY | openai/ |
| qwen-cn.json | qwen-plus | QWEN_CN_API_KEY | openai/ |
| zai-coding.json | glm-5.3 | ZAI_CODING_API_KEY | openai/ |
| minimax-cn.json | MiniMax-M3 | MINIMAX_CN_API_KEY | openai/ |

模型名以账户可调用目录为准。示例来源：[OpenAI GPT-4.1](https://developers.openai.com/api/docs/models/gpt-4.1)、[Claude Sonnet 5](https://platform.claude.com/docs/en/models/sonnet-5/whats-new-sonnet-5)、[Gemini 2.5 Pro](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro)、[DeepSeek API 更新](https://api-docs.deepseek.com/updates/)、[Qwen-Plus](https://help.aliyun.com/en/model-studio/qwen-plus)。Z.AI 和 MiniMax 示例与本次验证环境的实际模型相同；其余模型未使用真实厂商凭据逐一调用，不能据此保证所有账户均有访问权限。

以平台 ID `team-coder`、DeepSeek 示例为例，模型表单填写：提供商 `openai-compatible`、上游模型 `deepseek-v4-flash`、Base URL `https://api.deepseek.com`、自己的 key。服务器编译得到：

```json
{
  "model_name": "team-coder",
  "litellm_params": {
    "model": "openai/deepseek-v4-flash",
    "api_base": "https://api.deepseek.com",
    "api_key": "已脱敏"
  }
}
```

Agent 勾选并发布后，默认模型可对应：

```json
{
  "model": "cloud-model-gateway/team-coder",
  "provider": {
    "cloud-model-gateway": {
      "models": {"team-coder": {"name": "团队代码模型"}}
    }
  }
}
```

其他六个厂商使用同一映射规则，将表格中的前缀和上游模型代入；端点按模板填写。Qwen 中国/国际、MiniMax 国内/国际、Z.AI Coding/普通 API 使用不同端点与账户配置，不能混用。浏览器预览调用服务器编译器，显示最终具体条目；示例仅用于理解字段。

保存后依次发布模型网关、分配给 Agent、设置默认/小模型、发布 Agent。新模型不会自动进入其他 Agent。
