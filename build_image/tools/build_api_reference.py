"""Render public API Markdown from a module-name -> OpenAPI document JSON file.

Input: authenticated GET /openapi.json from each internal service, keyed by
catalog_service, operations, file_service, observability, etc. Never pass tokens
in the input: it contains schemas only. This tool performs no network requests.
Run from the source checkout: python build_image/tools/build_api_reference.py
    --schemas /path/to/schemas.json
"""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from operations.src.requests import OperationRequest, SandboxRequest, DeleteRequest
from catalog_service.src.admin_dto import ModelWrite

METHODS = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options'}


def code(value):
    return '```json\n' + json.dumps(value, ensure_ascii=False, indent=2) + '\n```\n'


def render(documents):
    out = ['# 对外 API 完整参考\n',
           f'本文件配合 [API 使用手册](api.md) 使用。结构快照：2026-09-16，平台 {(ROOT / "VERSION").read_text().strip()}。',
           '公共前缀为手册中的 `BASE_URL`；所有业务接口使用 `Authorization: Bearer <ADMIN_TOKEN>`。',
           '参数标注来自服务 OpenAPI；自由对象和运行时校验补充见手册。响应 schema 为 `{}` 表示服务尚未声明响应模型，**不表示没有响应或响应必为空对象**。HTTP 错误及异步状态以手册为准。',
           '生成方式：收集内部服务的 `/openapi.json` 为按模块名组织的 JSON，再执行 `python build_image/tools/build_api_reference.py --schemas schemas.json`。输入只含结构，不含运行凭据。\n']
    count = 0
    for module in ['catalog_service', 'operations', 'file_service', 'observability']:
        document = copy.deepcopy(documents[module])
        definitions = document.get('components', {}).get('schemas', {})
        # These routes use dict bodies and validate them inside the handler.
        for model in [OperationRequest, SandboxRequest, DeleteRequest, ModelWrite]:
            schema = model.model_json_schema(ref_template='#/components/schemas/{model}')
            definitions.update(schema.pop('$defs', {}))
            definitions[model.__name__] = schema
        used = set()

        def refs(value):
            if isinstance(value, dict):
                if '$ref' in value:
                    name = value['$ref'].rsplit('/', 1)[-1]
                    if name not in used and name in definitions:
                        used.add(name)
                        refs(definitions[name])
                for v in value.values(): refs(v)
            elif isinstance(value, list):
                for v in value: refs(v)

        out.append('## ' + module + '\n')
        for path, item in sorted(document['paths'].items()):
            if not path.startswith('/cloud/'):
                continue
            for method, original in item.items():
                if method not in METHODS: continue
                variants = [path]
                if path == '/cloud/admin/sandboxes/{sid}/{action}':
                    variants = [path.replace('{action}', a) for a in ('start', 'stop', 'restart', 'destroy')]
                if path == '/cloud/admin/agents/{aid}/{action}':
                    variants = [path.replace('{action}', a) for a in ('archive', 'restore', 'delete', 'delete-empty')]
                for actual in variants:
                    operation = copy.deepcopy(original)
                    body_model = None
                    if '{action}' in path:
                        body_model = (DeleteRequest if actual.endswith('/delete') else
                                      SandboxRequest if '/sandboxes/' in actual and not actual.endswith('/start') else OperationRequest)
                    if module == 'catalog_service' and actual in ('/cloud/admin/models/test-draft', '/cloud/admin/models/config-preview'):
                        body_model = ModelWrite
                    if body_model:
                        operation['requestBody'] = {'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/' + body_model.__name__}}}}
                    count += 1
                    out.append('### ' + method.upper() + ' `' + actual + '`\n')
                    params = [p for p in item.get('parameters', []) + operation.get('parameters', []) if p['name'] != 'action']
                    if params:
                        out.extend(['| 参数 | 位置 | 必填 | 类型、默认值与边界 |', '| --- | --- | --- | --- |'])
                        for p in params:
                            details = json.dumps(p.get('schema', {}), ensure_ascii=False).replace('|', '&#124;')
                            out.append(f"| `{p['name']}` | {p['in']} | {'是' if p.get('required') else '否'} | `{details}` |")
                        out.append('')
                    else: out.append('Path / Query 参数：无。\n')
                    body = operation.get('requestBody')
                    if body:
                        out.append('Body：' + ('必填' if body.get('required') else '可选') + '。`$ref` 对应本模块后面的类型定义。\n')
                        out.append(code(body['content']))
                    else: out.append('Body：无。\n')
                    out.append('响应（未显式列出的错误仍可能返回，见手册）：\n')
                    out.append(code(operation.get('responses', {})))
                    refs(operation)
        out.append('### ' + module + ' 请求和响应类型\n')
        out.append('同名类型只在当前模块内解析。`required` 为必填字段，`default` 为默认值；`additionalProperties:false` 表示拒绝未知字段。\n')
        for name in sorted(used):
            out.append('#### `' + name + '`\n')
            out.append(code(definitions[name]))

    out.extend(['## 网关入口与模型推理\n',
        '| 方法 | URL | 请求与响应 |', '| --- | --- | --- |',
        '| GET | `/cloud/health`、`/health/live` | 无需认证，`{"ok":true}` |',
        '| GET | `/cloud/health/ready` | 管理员认证，`ok` 与 `modules` 健康状态，失败 503 |',
        '| GET | `/metrics` | 管理员认证，Prometheus 文本 |',
        '| GET | `/doc` | 管理员认证，OpenCode JSON schema 与路由扩展 |',
        '| GET | `/openapi.json` | 管理员认证，网关本身的 schema |',
        '| GET | `/docs`、`/redoc` | 管理员认证，网关文档 HTML；不是完整聚合接口文档 |',
        '| GET | `/llm/v1/models` | 管理员认证，OpenAI 风格模型列表 |',
        '| POST | `/llm/v1/chat/completions` | `model`、`messages`，可选 `stream`；completion JSON 或 SSE |',
        '| POST | `/llm/v1/completions` | `model`、`prompt` 及供应商支持参数 |',
        '| POST | `/llm/v1/embeddings` | `model`、`input` 及供应商支持参数 |',
        '| POST | `/llm/v1/responses` | `model`、`input` 及供应商支持参数 |',
        '| POST | `/llm/v1/rerank` | `model`、`query`、`documents` 及供应商支持参数 |\n',
        '这些模型接口使用 JSON，自由字段透传给 LiteLLM；能力由上游模型决定。不存在通用 `POST /llm/v1/*` 任意代理能力。\n',
        '## 原生 OpenCode 接口\n',
        '以下来自固定 OpenCode 1.18.29 schema，公共路径不加 `/cloud`。认证和 Agent/用户/会话路由 Header 见手册第 1 节。',
        '**兼容边界：此清单描述上游协议，不保证平台开放所有上游能力。** 平台管理的 config/auth/MCP 写操作会被拒绝；项目、工作树、终端和全局操作取决于沙箱运行条件。优先使用手册中已说明的平台管理、文件及会话流程。',
        '每个请求的 schema 内 `$ref` 指向 [固定原生 schema 的 components/schemas](../api_gateway/resources/upstream/opencode-1.18.29-openapi.json)。该文件同时包含完整响应字段和枚举。\n'])
    native = json.loads((ROOT / 'api_gateway/resources/upstream/opencode-1.18.29-openapi.json').read_text(encoding='utf-8'))
    native_count = 0
    for path, item in sorted(native['paths'].items()):
        for method, operation in item.items():
            if method not in METHODS: continue
            native_count += 1
            out.append('### ' + method.upper() + ' `' + path + '`\n')
            out.append(operation.get('summary', operation.get('operationId', '')) + '\n')
            contract = {key: operation[key] for key in ('parameters', 'requestBody', 'responses') if key in operation}
            out.append('<details><summary>参数、Body 和响应结构</summary>\n')
            out.append(code(contract))
            out.append('</details>\n')
    out.append(f'平台业务操作共 {count} 项（另列网关/推理入口）；原生协议操作 {native_count} 项。\n')
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schemas', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/api-reference.md')
    args = parser.parse_args()
    args.output.write_text(render(json.loads(args.schemas.read_text(encoding='utf-8'))), encoding='utf-8')
    print(args.output)


if __name__ == '__main__': main()
