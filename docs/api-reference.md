# 对外 API 完整参考

本文件配合 [API 使用手册](api.md) 使用。结构快照：2026-09-16，平台 0.3.7。
公共前缀为手册中的 `BASE_URL`；所有业务接口使用 `Authorization: Bearer <ADMIN_TOKEN>`。
参数标注来自服务 OpenAPI；自由对象和运行时校验补充见手册。响应 schema 为 `{}` 表示服务尚未声明响应模型，**不表示没有响应或响应必为空对象**。HTTP 错误及异步状态以手册为准。
生成方式：收集内部服务的 `/openapi.json` 为按模块名组织的 JSON，再执行 `python build_image/tools/build_api_reference.py --schemas schemas.json`。输入只含结构，不含运行凭据。

## catalog_service

### GET `/cloud/admin/agent-templates`

Path / Query 参数：无。

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  }
}
```

### POST `/cloud/admin/agent-templates/{tid}/restore`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `tid` | path | 是 | `{"type": "string", "title": "Tid"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/TemplateRestore"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/agents`

Path / Query 参数：无。

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  }
}
```

### PUT `/cloud/admin/agents/{agent_id}`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `agent_id` | path | 是 | `{"type": "string", "title": "Agent Id"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/AgentWrite"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### PUT `/cloud/admin/agents/{agent_id}/bindings`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `agent_id` | path | 是 | `{"type": "string", "title": "Agent Id"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/BindingWrite"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/agents/{agent_id}/config-preview`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `agent_id` | path | 是 | `{"type": "string", "title": "Agent Id"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/AgentWrite"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/agents/{agent_id}/copy`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `agent_id` | path | 是 | `{"type": "string", "title": "Agent Id"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/CopyRequest"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/agents/{agent_id}/effective-config`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `agent_id` | path | 是 | `{"type": "string", "title": "Agent Id"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/catalog`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `compact` | query | 否 | `{"type": "boolean", "default": false, "title": "Compact"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/config-preview`

Path / Query 参数：无。

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  }
}
```

### POST `/cloud/admin/exports/encrypted`

Path / Query 参数：无。

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/EncryptedExport"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/exports/native/{aid}`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `aid` | path | 是 | `{"type": "string", "title": "Aid"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/exports/resources`

Path / Query 参数：无。

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  }
}
```

### POST `/cloud/admin/imports/preview`

Path / Query 参数：无。

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "multipart/form-data": {
    "schema": {
      "$ref": "#/components/schemas/Body_preview_cloud_admin_imports_preview_post"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/imports/{preview_id}/commit`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `preview_id` | path | 是 | `{"type": "string", "title": "Preview Id"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/ImportCommit"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/models`

Path / Query 参数：无。

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  }
}
```

### POST `/cloud/admin/models/config-preview`

Path / Query 参数：无。

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/ModelWrite"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/models/import`

Path / Query 参数：无。

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/ModelImport"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/models/test-draft`

Path / Query 参数：无。

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/ModelWrite"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### PUT `/cloud/admin/models/{model_id}`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `model_id` | path | 是 | `{"type": "string", "title": "Model Id"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/ModelWrite"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### DELETE `/cloud/admin/models/{model_id}`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `model_id` | path | 是 | `{"type": "string", "title": "Model Id"}` |
| `revision` | query | 否 | `{"anyOf": [{"type": "integer"}, {"type": "null"}], "title": "Revision"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/models/{model_id}/test`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `model_id` | path | 是 | `{"type": "string", "title": "Model Id"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/provider-templates`

Path / Query 参数：无。

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  }
}
```

### GET `/cloud/admin/resources`

Path / Query 参数：无。

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  }
}
```

### PUT `/cloud/admin/resources/{resource_id}`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `resource_id` | path | 是 | `{"type": "string", "title": "Resource Id"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/ResourceWrite"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### DELETE `/cloud/admin/resources/{resource_id}`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `resource_id` | path | 是 | `{"type": "string", "title": "Resource Id"}` |
| `revision` | query | 否 | `{"anyOf": [{"type": "integer"}, {"type": "null"}], "title": "Revision"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/resources/{resource_id}/archive`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `resource_id` | path | 是 | `{"type": "string", "title": "Resource Id"}` |

Body：可选。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/Revision",
      "default": {}
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/resources/{resource_id}/copy`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `resource_id` | path | 是 | `{"type": "string", "title": "Resource Id"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/CopyRequest"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/resources/{resource_id}/file`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `resource_id` | path | 是 | `{"type": "string", "title": "Resource Id"}` |
| `path` | query | 是 | `{"type": "string", "title": "Path"}` |
| `version` | query | 否 | `{"anyOf": [{"type": "integer"}, {"type": "null"}], "title": "Version"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/resources/{resource_id}/publish`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `resource_id` | path | 是 | `{"type": "string", "title": "Resource Id"}` |

Body：可选。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/ProbeRequest",
      "default": {}
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/resources/{resource_id}/restore`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `resource_id` | path | 是 | `{"type": "string", "title": "Resource Id"}` |

Body：可选。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/Revision",
      "default": {}
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/resources/{resource_id}/test`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `resource_id` | path | 是 | `{"type": "string", "title": "Resource Id"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/ProbeRequest"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/resources/{resource_id}/upload`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `resource_id` | path | 是 | `{"type": "string", "title": "Resource Id"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "multipart/form-data": {
    "schema": {
      "$ref": "#/components/schemas/Body_upload_skill_cloud_admin_resources__resource_id__upload_post"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/resources/{resource_id}/versions`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `resource_id` | path | 是 | `{"type": "string", "title": "Resource Id"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/agents`

Path / Query 参数：无。

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  }
}
```

### GET `/cloud/capabilities`

Path / Query 参数：无。

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  }
}
```

### GET `/cloud/models`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `agent_id` | query | 否 | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Agent Id"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### catalog_service 请求和响应类型

同名类型只在当前模块内解析。`required` 为必填字段，`default` 为默认值；`additionalProperties:false` 表示拒绝未知字段。

#### `AgentDefinition`

```json
{
  "properties": {
    "name": {
      "type": "string",
      "maxLength": 200,
      "minLength": 1,
      "title": "Name"
    },
    "description": {
      "type": "string",
      "maxLength": 4000,
      "title": "Description",
      "default": ""
    },
    "enabled": {
      "type": "boolean",
      "title": "Enabled",
      "default": true
    },
    "instructions": {
      "type": "string",
      "maxLength": 200000,
      "title": "Instructions",
      "default": ""
    },
    "allowed_model_ids": {
      "items": {
        "type": "string",
        "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$"
      },
      "type": "array",
      "minItems": 1,
      "title": "Allowed Model Ids"
    },
    "default_model_id": {
      "type": "string",
      "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",
      "title": "Default Model Id"
    },
    "small_model_id": {
      "anyOf": [
        {
          "type": "string",
          "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$"
        },
        {
          "type": "null"
        }
      ],
      "title": "Small Model Id"
    },
    "cpu_limit": {
      "anyOf": [
        {
          "type": "integer",
          "enum": [
            1,
            2,
            4,
            8
          ]
        },
        {
          "type": "null"
        }
      ],
      "title": "Cpu Limit"
    },
    "memory_mb": {
      "anyOf": [
        {
          "type": "integer",
          "enum": [
            1024,
            2048,
            4096,
            8192
          ]
        },
        {
          "type": "null"
        }
      ],
      "title": "Memory Mb"
    },
    "bindings": {
      "items": {
        "$ref": "#/components/schemas/VersionBinding"
      },
      "type": "array",
      "title": "Bindings"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "name",
    "allowed_model_ids",
    "default_model_id"
  ],
  "title": "AgentDefinition"
}
```

#### `AgentWrite`

```json
{
  "properties": {
    "revision": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Revision"
    },
    "config": {
      "$ref": "#/components/schemas/AgentDefinition"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "config"
  ],
  "title": "AgentWrite"
}
```

#### `BindingWrite`

```json
{
  "properties": {
    "revision": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Revision"
    },
    "bindings": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/components/schemas/VersionBinding"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Bindings"
    },
    "allowed_model_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string",
            "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "title": "Allowed Model Ids"
    },
    "default_model_id": {
      "anyOf": [
        {
          "type": "string",
          "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$"
        },
        {
          "type": "null"
        }
      ],
      "title": "Default Model Id"
    },
    "small_model_id": {
      "anyOf": [
        {
          "type": "string",
          "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$"
        },
        {
          "type": "null"
        }
      ],
      "title": "Small Model Id"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "BindingWrite"
}
```

#### `Body_preview_cloud_admin_imports_preview_post`

```json
{
  "properties": {
    "file": {
      "type": "string",
      "format": "binary",
      "title": "File"
    },
    "password": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Password"
    }
  },
  "type": "object",
  "required": [
    "file"
  ],
  "title": "Body_preview_cloud_admin_imports_preview_post"
}
```

#### `Body_upload_skill_cloud_admin_resources__resource_id__upload_post`

```json
{
  "properties": {
    "file": {
      "type": "string",
      "format": "binary",
      "title": "File"
    },
    "owner": {
      "type": "string",
      "title": "Owner",
      "default": ""
    },
    "revision": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Revision"
    }
  },
  "type": "object",
  "required": [
    "file"
  ],
  "title": "Body_upload_skill_cloud_admin_resources__resource_id__upload_post"
}
```

#### `CopyRequest`

```json
{
  "properties": {
    "revision": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Revision"
    },
    "id": {
      "type": "string",
      "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",
      "title": "Id"
    },
    "owner": {
      "anyOf": [
        {
          "type": "string",
          "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$"
        },
        {
          "type": "null"
        }
      ],
      "title": "Owner"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "id"
  ],
  "title": "CopyRequest"
}
```

#### `EncryptedExport`

```json
{
  "properties": {
    "password": {
      "type": "string",
      "maxLength": 1024,
      "minLength": 12,
      "title": "Password"
    },
    "include_credentials": {
      "type": "boolean",
      "title": "Include Credentials",
      "default": false
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "password"
  ],
  "title": "EncryptedExport"
}
```

#### `HTTPValidationError`

```json
{
  "properties": {
    "detail": {
      "items": {
        "$ref": "#/components/schemas/ValidationError"
      },
      "type": "array",
      "title": "Detail"
    }
  },
  "type": "object",
  "title": "HTTPValidationError"
}
```

#### `ImportCommit`

```json
{
  "properties": {
    "selections": {
      "items": {
        "$ref": "#/components/schemas/Selection"
      },
      "type": "array",
      "maxItems": 1000,
      "minItems": 1,
      "title": "Selections"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "selections"
  ],
  "title": "ImportCommit"
}
```

#### `ModelDefinition`

```json
{
  "additionalProperties": false,
  "properties": {
    "id": {
      "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",
      "title": "Id",
      "type": "string"
    },
    "name": {
      "default": "",
      "title": "Name",
      "type": "string"
    },
    "provider": {
      "enum": [
        "openai-compatible",
        "openai",
        "anthropic",
        "google",
        "legacy"
      ],
      "title": "Provider",
      "type": "string"
    },
    "upstream_model": {
      "minLength": 1,
      "title": "Upstream Model",
      "type": "string"
    },
    "base_url": {
      "default": "",
      "title": "Base Url",
      "type": "string"
    },
    "additional_base_urls": {
      "items": {
        "type": "string"
      },
      "maxItems": 7,
      "title": "Additional Base Urls",
      "type": "array"
    },
    "api_key": {
      "default": "",
      "title": "Api Key",
      "type": "string"
    },
    "deployments": {
      "items": {
        "$ref": "#/components/schemas/ModelDeployment"
      },
      "maxItems": 32,
      "title": "Deployments",
      "type": "array"
    },
    "headers": {
      "additionalProperties": {
        "type": "string"
      },
      "title": "Headers",
      "type": "object"
    },
    "parameters": {
      "additionalProperties": {
        "anyOf": [
          {
            "type": "integer"
          },
          {
            "type": "number"
          },
          {
            "type": "string"
          }
        ]
      },
      "title": "Parameters",
      "type": "object"
    },
    "context": {
      "anyOf": [
        {
          "exclusiveMinimum": 0,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Context"
    },
    "output": {
      "anyOf": [
        {
          "exclusiveMinimum": 0,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Output"
    },
    "enabled": {
      "default": true,
      "title": "Enabled",
      "type": "boolean"
    },
    "legacy": {
      "default": false,
      "title": "Legacy",
      "type": "boolean"
    }
  },
  "required": [
    "id",
    "provider",
    "upstream_model"
  ],
  "title": "ModelDefinition",
  "type": "object"
}
```

#### `ModelDeployment`

```json
{
  "additionalProperties": false,
  "properties": {
    "id": {
      "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",
      "title": "Id",
      "type": "string"
    },
    "api_key": {
      "default": "",
      "title": "Api Key",
      "type": "string"
    },
    "base_url": {
      "default": "",
      "title": "Base Url",
      "type": "string"
    },
    "upstream_model": {
      "default": "",
      "title": "Upstream Model",
      "type": "string"
    },
    "headers": {
      "additionalProperties": {
        "type": "string"
      },
      "title": "Headers",
      "type": "object"
    },
    "enabled": {
      "default": true,
      "title": "Enabled",
      "type": "boolean"
    },
    "rpm": {
      "anyOf": [
        {
          "exclusiveMinimum": 0,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Rpm"
    },
    "tpm": {
      "anyOf": [
        {
          "exclusiveMinimum": 0,
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Tpm"
    },
    "weight": {
      "anyOf": [
        {
          "exclusiveMinimum": 0,
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Weight"
    }
  },
  "required": [
    "id"
  ],
  "title": "ModelDeployment",
  "type": "object"
}
```

#### `ModelImport`

```json
{
  "properties": {
    "revision": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Revision"
    },
    "models": {
      "items": {
        "$ref": "#/components/schemas/ModelDefinition"
      },
      "type": "array",
      "maxItems": 100,
      "minItems": 1,
      "title": "Models"
    },
    "replace": {
      "type": "boolean",
      "title": "Replace",
      "default": false
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "models"
  ],
  "title": "ModelImport"
}
```

#### `ModelWrite`

```json
{
  "additionalProperties": false,
  "properties": {
    "revision": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Revision"
    },
    "model": {
      "$ref": "#/components/schemas/ModelDefinition"
    }
  },
  "required": [
    "model"
  ],
  "title": "ModelWrite",
  "type": "object"
}
```

#### `ProbeRequest`

```json
{
  "properties": {
    "agent_id": {
      "anyOf": [
        {
          "type": "string",
          "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$"
        },
        {
          "type": "null"
        }
      ],
      "title": "Agent Id"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "ProbeRequest"
}
```

#### `ResourceDefinition`

```json
{
  "properties": {
    "kind": {
      "type": "string",
      "enum": [
        "mcp",
        "skill",
        "hook"
      ],
      "title": "Kind"
    },
    "name": {
      "type": "string",
      "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",
      "title": "Name"
    },
    "owner": {
      "anyOf": [
        {
          "type": "string",
          "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$"
        },
        {
          "type": "null"
        }
      ],
      "title": "Owner"
    },
    "archived": {
      "type": "boolean",
      "title": "Archived",
      "default": false
    },
    "data": {
      "additionalProperties": true,
      "type": "object",
      "title": "Data"
    }
  },
  "type": "object",
  "required": [
    "kind",
    "name",
    "data"
  ],
  "title": "ResourceDefinition"
}
```

#### `ResourceWrite`

```json
{
  "properties": {
    "revision": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Revision"
    },
    "resource": {
      "$ref": "#/components/schemas/ResourceDefinition"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "resource"
  ],
  "title": "ResourceWrite"
}
```

#### `Revision`

```json
{
  "properties": {
    "revision": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Revision"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "Revision"
}
```

#### `Selection`

```json
{
  "properties": {
    "key": {
      "type": "string",
      "title": "Key"
    },
    "target_id": {
      "type": "string",
      "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",
      "title": "Target Id"
    },
    "replace": {
      "type": "boolean",
      "title": "Replace",
      "default": false
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "key",
    "target_id"
  ],
  "title": "Selection"
}
```

#### `TemplateRestore`

```json
{
  "properties": {
    "agent_id": {
      "type": "string",
      "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",
      "title": "Agent Id"
    },
    "models": {
      "additionalProperties": {
        "type": "string",
        "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$"
      },
      "type": "object",
      "title": "Models"
    },
    "resources": {
      "additionalProperties": {
        "$ref": "#/components/schemas/VersionBinding"
      },
      "type": "object",
      "title": "Resources"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "agent_id"
  ],
  "title": "TemplateRestore"
}
```

#### `ValidationError`

```json
{
  "properties": {
    "loc": {
      "items": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "integer"
          }
        ]
      },
      "type": "array",
      "title": "Location"
    },
    "msg": {
      "type": "string",
      "title": "Message"
    },
    "type": {
      "type": "string",
      "title": "Error Type"
    }
  },
  "type": "object",
  "required": [
    "loc",
    "msg",
    "type"
  ],
  "title": "ValidationError"
}
```

#### `VersionBinding`

```json
{
  "properties": {
    "id": {
      "type": "string",
      "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",
      "title": "Id"
    },
    "version": {
      "type": "integer",
      "exclusiveMinimum": 0.0,
      "title": "Version"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "id",
    "version"
  ],
  "title": "VersionBinding"
}
```

## operations

### POST `/cloud/admin/agents/{aid}/apply`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `aid` | path | 是 | `{"type": "string", "title": "Aid"}` |

Body：可选。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/ApplyRequest",
      "default": {}
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/agents/{aid}/delete-preview`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `aid` | path | 是 | `{"type": "string", "title": "Aid"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/agents/{aid}/rollback`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `aid` | path | 是 | `{"type": "string", "title": "Aid"}` |

Body：可选。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/ApplyRequest",
      "default": {}
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/agents/{aid}/archive`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `aid` | path | 是 | `{"type": "string", "title": "Aid"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/OperationRequest"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/agents/{aid}/restore`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `aid` | path | 是 | `{"type": "string", "title": "Aid"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/OperationRequest"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/agents/{aid}/delete`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `aid` | path | 是 | `{"type": "string", "title": "Aid"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/DeleteRequest"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/agents/{aid}/delete-empty`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `aid` | path | 是 | `{"type": "string", "title": "Aid"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/OperationRequest"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/jobs`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `offset` | query | 否 | `{"type": "integer", "minimum": 0, "default": 0, "title": "Offset"}` |
| `limit` | query | 否 | `{"type": "integer", "maximum": 100, "minimum": 1, "default": 25, "title": "Limit"}` |
| `target` | query | 否 | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Target"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/jobs/export`

Path / Query 参数：无。

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  }
}
```

### GET `/cloud/admin/jobs/{jid}`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `jid` | path | 是 | `{"type": "string", "title": "Jid"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/jobs/{jid}/cancel`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `jid` | path | 是 | `{"type": "string", "title": "Jid"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/jobs/{jid}/reconcile`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `jid` | path | 是 | `{"type": "string", "title": "Jid"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/OperationRequest"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/jobs/{jid}/retry`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `jid` | path | 是 | `{"type": "string", "title": "Jid"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/DeleteRequest"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/load-tests`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `offset` | query | 否 | `{"type": "integer", "minimum": 0, "default": 0, "title": "Offset"}` |
| `limit` | query | 否 | `{"type": "integer", "maximum": 100, "minimum": 1, "default": 25, "title": "Limit"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/load-tests`

Path / Query 参数：无。

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/LoadRequest"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "202": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/load-tests/capacity`

Path / Query 参数：无。

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  }
}
```

### GET `/cloud/admin/load-tests/options`

Path / Query 参数：无。

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  }
}
```

### GET `/cloud/admin/load-tests/{rid}`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `rid` | path | 是 | `{"type": "string", "title": "Rid"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/load-tests/{rid}/cancel`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `rid` | path | 是 | `{"type": "string", "title": "Rid"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "202": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/load-tests/{rid}/cleanup`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `rid` | path | 是 | `{"type": "string", "title": "Rid"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/CleanupRequest"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "202": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/load-tests/{rid}/report`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `rid` | path | 是 | `{"type": "string", "title": "Rid"}` |
| `format` | query | 否 | `{"enum": ["json", "csv"], "type": "string", "default": "json", "title": "Format"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/models/apply`

Path / Query 参数：无。

Body：可选。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/ApplyRequest",
      "default": {}
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/recovery-policy`

Path / Query 参数：无。

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  }
}
```

### PUT `/cloud/admin/recovery-policy`

Path / Query 参数：无。

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/RecoveryPolicy"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/sandboxes`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `q` | query | 否 | `{"type": "string", "default": "", "title": "Q"}` |
| `status` | query | 否 | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Status"}` |
| `offset` | query | 否 | `{"type": "integer", "minimum": 0, "default": 0, "title": "Offset"}` |
| `limit` | query | 否 | `{"type": "integer", "maximum": 100, "minimum": 1, "default": 50, "title": "Limit"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/sandboxes/{sid}`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `sid` | path | 是 | `{"type": "string", "title": "Sid"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/admin/sandboxes/{sid}/force-preview`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `sid` | path | 是 | `{"type": "string", "title": "Sid"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/sandboxes/{sid}/start`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `sid` | path | 是 | `{"type": "string", "title": "Sid"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/OperationRequest"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/sandboxes/{sid}/stop`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `sid` | path | 是 | `{"type": "string", "title": "Sid"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/SandboxRequest"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/sandboxes/{sid}/restart`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `sid` | path | 是 | `{"type": "string", "title": "Sid"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/SandboxRequest"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/admin/sandboxes/{sid}/destroy`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `sid` | path | 是 | `{"type": "string", "title": "Sid"}` |

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "application/json": {
    "schema": {
      "$ref": "#/components/schemas/SandboxRequest"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/operations/security-status`

Path / Query 参数：无。

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  }
}
```

### operations 请求和响应类型

同名类型只在当前模块内解析。`required` 为必填字段，`default` 为默认值；`additionalProperties:false` 表示拒绝未知字段。

#### `ApplyRequest`

```json
{
  "properties": {
    "request_id": {
      "anyOf": [
        {
          "type": "string",
          "maxLength": 128,
          "minLength": 8
        },
        {
          "type": "null"
        }
      ],
      "title": "Request Id"
    },
    "revision": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "title": "Revision"
    },
    "version": {
      "anyOf": [
        {
          "type": "integer",
          "minimum": 1.0
        },
        {
          "type": "null"
        }
      ],
      "title": "Version"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "ApplyRequest"
}
```

#### `CleanupRequest`

```json
{
  "properties": {
    "confirmation": {
      "type": "string",
      "title": "Confirmation"
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "confirmation"
  ],
  "title": "CleanupRequest"
}
```

#### `DeleteRequest`

```json
{
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "maxLength": 128,
      "minLength": 8,
      "title": "Request Id",
      "type": "string"
    },
    "revision": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Revision"
    },
    "preview_id": {
      "title": "Preview Id",
      "type": "string"
    },
    "confirmation": {
      "title": "Confirmation",
      "type": "string"
    }
  },
  "required": [
    "request_id",
    "preview_id",
    "confirmation"
  ],
  "title": "DeleteRequest",
  "type": "object"
}
```

#### `HTTPValidationError`

```json
{
  "properties": {
    "detail": {
      "items": {
        "$ref": "#/components/schemas/ValidationError"
      },
      "type": "array",
      "title": "Detail"
    }
  },
  "type": "object",
  "title": "HTTPValidationError"
}
```

#### `LoadAgent`

```json
{
  "properties": {
    "agent_id": {
      "type": "string",
      "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",
      "title": "Agent Id"
    },
    "users": {
      "type": "integer",
      "maximum": 100.0,
      "minimum": 1.0,
      "title": "Users",
      "default": 1
    },
    "cpu_limit": {
      "type": "number",
      "maximum": 64.0,
      "minimum": 0.25,
      "title": "Cpu Limit",
      "default": 1
    },
    "memory_mb": {
      "type": "integer",
      "maximum": 65536.0,
      "minimum": 256.0,
      "title": "Memory Mb",
      "default": 1024
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "agent_id"
  ],
  "title": "LoadAgent"
}
```

#### `LoadRequest`

```json
{
  "properties": {
    "request_id": {
      "type": "string",
      "maxLength": 128,
      "minLength": 8,
      "title": "Request Id"
    },
    "agents": {
      "items": {
        "$ref": "#/components/schemas/LoadAgent"
      },
      "type": "array",
      "maxItems": 32,
      "minItems": 1,
      "title": "Agents"
    },
    "timeout_seconds": {
      "type": "integer",
      "maximum": 1800.0,
      "minimum": 10.0,
      "title": "Timeout Seconds",
      "default": 180
    },
    "prepare_timeout_seconds": {
      "type": "integer",
      "maximum": 300.0,
      "minimum": 10.0,
      "title": "Prepare Timeout Seconds",
      "default": 120
    }
  },
  "additionalProperties": false,
  "type": "object",
  "required": [
    "request_id",
    "agents"
  ],
  "title": "LoadRequest"
}
```

#### `OperationRequest`

```json
{
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "maxLength": 128,
      "minLength": 8,
      "title": "Request Id",
      "type": "string"
    },
    "revision": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Revision"
    }
  },
  "required": [
    "request_id"
  ],
  "title": "OperationRequest",
  "type": "object"
}
```

#### `RecoveryPolicy`

```json
{
  "properties": {
    "enabled": {
      "type": "boolean",
      "title": "Enabled",
      "default": true
    },
    "failure_threshold": {
      "type": "integer",
      "maximum": 20.0,
      "minimum": 1.0,
      "title": "Failure Threshold",
      "default": 3
    },
    "max_attempts": {
      "type": "integer",
      "maximum": 10.0,
      "minimum": 1.0,
      "title": "Max Attempts",
      "default": 3
    },
    "window_seconds": {
      "type": "integer",
      "maximum": 86400.0,
      "minimum": 60.0,
      "title": "Window Seconds",
      "default": 900
    },
    "backoff_seconds": {
      "items": {
        "type": "integer"
      },
      "type": "array",
      "maxItems": 10,
      "minItems": 1,
      "title": "Backoff Seconds"
    },
    "stable_seconds": {
      "type": "integer",
      "maximum": 3600.0,
      "minimum": 30.0,
      "title": "Stable Seconds",
      "default": 300
    },
    "agent_enabled": {
      "additionalProperties": {
        "type": "boolean"
      },
      "type": "object",
      "title": "Agent Enabled"
    },
    "max_parallel_recoveries": {
      "type": "integer",
      "maximum": 2.0,
      "minimum": 1.0,
      "title": "Max Parallel Recoveries",
      "default": 2
    }
  },
  "additionalProperties": false,
  "type": "object",
  "title": "RecoveryPolicy"
}
```

#### `SandboxRequest`

```json
{
  "additionalProperties": false,
  "properties": {
    "request_id": {
      "maxLength": 128,
      "minLength": 8,
      "title": "Request Id",
      "type": "string"
    },
    "revision": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Revision"
    },
    "force_preview_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Force Preview Id"
    },
    "confirmation": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Confirmation"
    }
  },
  "required": [
    "request_id"
  ],
  "title": "SandboxRequest",
  "type": "object"
}
```

#### `ValidationError`

```json
{
  "properties": {
    "loc": {
      "items": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "integer"
          }
        ]
      },
      "type": "array",
      "title": "Location"
    },
    "msg": {
      "type": "string",
      "title": "Message"
    },
    "type": {
      "type": "string",
      "title": "Error Type"
    }
  },
  "type": "object",
  "required": [
    "loc",
    "msg",
    "type"
  ],
  "title": "ValidationError"
}
```

## file_service

### GET `/cloud/files/download`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `agent_id` | query | 是 | `{"type": "string", "title": "Agent Id"}` |
| `username` | query | 是 | `{"type": "string", "title": "Username"}` |
| `path` | query | 是 | `{"type": "string", "title": "Path"}` |
| `session_id` | query | 否 | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Session Id"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/files/list`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `agent_id` | query | 是 | `{"type": "string", "title": "Agent Id"}` |
| `username` | query | 是 | `{"type": "string", "title": "Username"}` |
| `path` | query | 否 | `{"type": "string", "default": ".", "title": "Path"}` |
| `session_id` | query | 否 | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Session Id"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "additionalProperties": true,
          "title": "Response List Files Cloud Files List Get"
        }
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### POST `/cloud/files/upload`

Path / Query 参数：无。

Body：必填。`$ref` 对应本模块后面的类型定义。

```json
{
  "multipart/form-data": {
    "schema": {
      "$ref": "#/components/schemas/Body_upload_cloud_files_upload_post"
    }
  }
}
```

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {
          "additionalProperties": true,
          "type": "object",
          "title": "Response Upload Cloud Files Upload Post"
        }
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### file_service 请求和响应类型

同名类型只在当前模块内解析。`required` 为必填字段，`default` 为默认值；`additionalProperties:false` 表示拒绝未知字段。

#### `Body_upload_cloud_files_upload_post`

```json
{
  "properties": {
    "agent_id": {
      "type": "string",
      "title": "Agent Id"
    },
    "username": {
      "type": "string",
      "title": "Username"
    },
    "file": {
      "type": "string",
      "format": "binary",
      "title": "File"
    },
    "session_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Session Id"
    },
    "relative_path": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Relative Path"
    }
  },
  "type": "object",
  "required": [
    "agent_id",
    "username",
    "file"
  ],
  "title": "Body_upload_cloud_files_upload_post"
}
```

#### `HTTPValidationError`

```json
{
  "properties": {
    "detail": {
      "items": {
        "$ref": "#/components/schemas/ValidationError"
      },
      "type": "array",
      "title": "Detail"
    }
  },
  "type": "object",
  "title": "HTTPValidationError"
}
```

#### `ValidationError`

```json
{
  "properties": {
    "loc": {
      "items": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "integer"
          }
        ]
      },
      "type": "array",
      "title": "Location"
    },
    "msg": {
      "type": "string",
      "title": "Message"
    },
    "type": {
      "type": "string",
      "title": "Error Type"
    }
  },
  "type": "object",
  "required": [
    "loc",
    "msg",
    "type"
  ],
  "title": "ValidationError"
}
```

## observability

### GET `/cloud/logs`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `module` | query | 否 | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Module"}` |
| `trace_id` | query | 否 | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Trace Id"}` |
| `job_id` | query | 否 | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Job Id"}` |
| `session_id` | query | 否 | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Session Id"}` |
| `limit` | query | 否 | `{"type": "integer", "maximum": 1000, "minimum": 1, "default": 100, "title": "Limit"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/logs/export`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `module` | query | 否 | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Module"}` |
| `trace_id` | query | 否 | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Trace Id"}` |
| `session_id` | query | 否 | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Session Id"}` |
| `job_id` | query | 否 | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Job Id"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/logs/modules`

Path / Query 参数：无。

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  }
}
```

### GET `/cloud/traces`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `trace_id` | query | 否 | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Trace Id"}` |
| `session_id` | query | 否 | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Session Id"}` |
| `exclude_health` | query | 否 | `{"type": "boolean", "default": true, "title": "Exclude Health"}` |
| `session_only` | query | 否 | `{"type": "boolean", "default": false, "title": "Session Only"}` |
| `limit` | query | 否 | `{"type": "integer", "maximum": 200, "minimum": 1, "default": 50, "title": "Limit"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/traces/sessions/{session_id}`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"type": "string", "title": "Session Id"}` |
| `limit` | query | 否 | `{"type": "integer", "maximum": 200, "minimum": 1, "default": 50, "title": "Limit"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### GET `/cloud/traces/{trace_id}`

| 参数 | 位置 | 必填 | 类型、默认值与边界 |
| --- | --- | --- | --- |
| `trace_id` | path | 是 | `{"type": "string", "title": "Trace Id"}` |

Body：无。

响应（未显式列出的错误仍可能返回，见手册）：

```json
{
  "200": {
    "description": "Successful Response",
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "422": {
    "description": "Validation Error",
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/HTTPValidationError"
        }
      }
    }
  }
}
```

### observability 请求和响应类型

同名类型只在当前模块内解析。`required` 为必填字段，`default` 为默认值；`additionalProperties:false` 表示拒绝未知字段。

#### `HTTPValidationError`

```json
{
  "properties": {
    "detail": {
      "items": {
        "$ref": "#/components/schemas/ValidationError"
      },
      "type": "array",
      "title": "Detail"
    }
  },
  "type": "object",
  "title": "HTTPValidationError"
}
```

#### `ValidationError`

```json
{
  "properties": {
    "loc": {
      "items": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "integer"
          }
        ]
      },
      "type": "array",
      "title": "Location"
    },
    "msg": {
      "type": "string",
      "title": "Message"
    },
    "type": {
      "type": "string",
      "title": "Error Type"
    }
  },
  "type": "object",
  "required": [
    "loc",
    "msg",
    "type"
  ],
  "title": "ValidationError"
}
```

## 网关入口与模型推理

| 方法 | URL | 请求与响应 |
| --- | --- | --- |
| GET | `/cloud/health`、`/health/live` | 无需认证，`{"ok":true}` |
| GET | `/cloud/health/ready` | 管理员认证，`ok` 与 `modules` 健康状态，失败 503 |
| GET | `/metrics` | 管理员认证，Prometheus 文本 |
| GET | `/doc` | 管理员认证，OpenCode JSON schema 与路由扩展 |
| GET | `/openapi.json` | 管理员认证，网关本身的 schema |
| GET | `/docs`、`/redoc` | 管理员认证，网关文档 HTML；不是完整聚合接口文档 |
| GET | `/llm/v1/models` | 管理员认证，OpenAI 风格模型列表 |
| POST | `/llm/v1/chat/completions` | `model`、`messages`，可选 `stream`；completion JSON 或 SSE |
| POST | `/llm/v1/completions` | `model`、`prompt` 及供应商支持参数 |
| POST | `/llm/v1/embeddings` | `model`、`input` 及供应商支持参数 |
| POST | `/llm/v1/responses` | `model`、`input` 及供应商支持参数 |
| POST | `/llm/v1/rerank` | `model`、`query`、`documents` 及供应商支持参数 |

这些模型接口使用 JSON，自由字段透传给 LiteLLM；能力由上游模型决定。不存在通用 `POST /llm/v1/*` 任意代理能力。

## 原生 OpenCode 接口

以下来自固定 OpenCode 1.18.29 schema，公共路径不加 `/cloud`。认证和 Agent/用户/会话路由 Header 见手册第 1 节。
**兼容边界：此清单描述上游协议，不保证平台开放所有上游能力。** 平台管理的 config/auth/MCP 写操作会被拒绝；项目、工作树、终端和全局操作取决于沙箱运行条件。优先使用手册中已说明的平台管理、文件及会话流程。
每个请求的 schema 内 `$ref` 指向 [固定原生 schema 的 components/schemas](../api_gateway/resources/upstream/opencode-1.18.29-openapi.json)。该文件同时包含完整响应字段和枚举。

### GET `/agent`

List agents

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "List of agents",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Agent"
            },
            "description": "List of agents"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/agent`

List agents

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/AgentV2Info"
                }
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/command`

List commands

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/CommandV2Info"
                }
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### PATCH `/api/credential/{credentialID}`

Update credential

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "credentialID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "label": {
              "type": "string"
            }
          },
          "required": [
            "label"
          ],
          "additionalProperties": false
        }
      }
    },
    "required": true
  },
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### DELETE `/api/credential/{credentialID}`

Remove credential

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "credentialID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/event`

Subscribe to events

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [],
  "responses": {
    "200": {
      "description": "Event stream",
      "content": {
        "text/event-stream": {
          "schema": {
            "$ref": "#/components/schemas/V2Event"
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/fs/find`

Find files

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    },
    {
      "name": "query",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "type",
      "in": "query",
      "schema": {
        "type": "string",
        "enum": [
          "file",
          "directory"
        ]
      },
      "required": false
    },
    {
      "name": "limit",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/FileSystemEntry"
                }
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/fs/list`

List directory

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    },
    {
      "name": "path",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/FileSystemEntry"
                }
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/fs/read/*`

Read file

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/octet-stream": {
          "schema": {
            "type": "string",
            "format": "binary"
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/health`

Check server health

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "healthy": {
                "type": "boolean",
                "enum": [
                  true
                ]
              }
            },
            "required": [
              "healthy"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/integration`

List integrations

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/IntegrationInfo"
                }
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/integration/attempt/{attemptID}`

Get OAuth attempt status

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "attemptID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "$ref": "#/components/schemas/IntegrationAttemptStatus"
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### DELETE `/api/integration/attempt/{attemptID}`

Cancel OAuth connection

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "attemptID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/integration/attempt/{attemptID}/complete`

Complete OAuth connection

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "attemptID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "code": {
              "type": "string"
            }
          },
          "additionalProperties": false
        }
      }
    },
    "required": true
  },
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/integration/{integrationID}`

Get integration

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "integrationID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "$ref": "#/components/schemas/IntegrationInfo"
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/integration/{integrationID}/connect/key`

Connect with key

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "integrationID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "key": {
              "type": "string"
            },
            "label": {
              "type": "string"
            }
          },
          "required": [
            "key"
          ],
          "additionalProperties": false
        }
      }
    },
    "required": true
  },
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/integration/{integrationID}/connect/oauth`

Begin OAuth connection

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "integrationID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "methodID": {
              "type": "string"
            },
            "inputs": {
              "type": "object",
              "additionalProperties": {
                "type": "string"
              }
            },
            "label": {
              "type": "string"
            }
          },
          "required": [
            "methodID",
            "inputs"
          ],
          "additionalProperties": false
        }
      }
    },
    "required": true
  },
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "$ref": "#/components/schemas/IntegrationAttempt"
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/location`

Get location

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Location.Info",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/LocationInfo"
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/model`

List models

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/ModelV2Info"
                }
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "503": {
      "description": "ServiceUnavailableError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ServiceUnavailableError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/permission/request`

List pending permission requests

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/PermissionV2Request"
                }
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/permission/saved`

List saved permissions

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "projectID",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/PermissionSavedInfo"
                }
              }
            },
            "required": [
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### DELETE `/api/permission/saved/{id}`

Remove saved permission

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "id",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    }
  ],
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/provider`

List providers

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/ProviderV2Info"
                }
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "503": {
      "description": "ServiceUnavailableError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ServiceUnavailableError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/provider/{providerID}`

Get provider

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "providerID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "$ref": "#/components/schemas/ProviderV2Info"
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "ProviderNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ProviderNotFoundError"
          }
        }
      }
    },
    "503": {
      "description": "ServiceUnavailableError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ServiceUnavailableError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/pty`

List PTY sessions

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/Pty"
                }
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/pty`

Create PTY session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "command": {
              "type": "string"
            },
            "args": {
              "type": "array",
              "items": {
                "type": "string"
              }
            },
            "cwd": {
              "type": "string"
            },
            "title": {
              "type": "string"
            },
            "env": {
              "type": "object",
              "additionalProperties": {
                "type": "string"
              }
            }
          },
          "additionalProperties": false
        }
      }
    },
    "required": true
  },
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "$ref": "#/components/schemas/Pty"
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/pty/{ptyID}`

Get PTY session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "ptyID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^pty"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "$ref": "#/components/schemas/Pty"
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "PtyNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/PtyNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### PUT `/api/pty/{ptyID}`

Update PTY session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "ptyID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^pty"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "title": {
              "type": "string"
            },
            "size": {
              "type": "object",
              "properties": {
                "rows": {
                  "type": "integer",
                  "exclusiveMinimum": 0
                },
                "cols": {
                  "type": "integer",
                  "exclusiveMinimum": 0
                }
              },
              "required": [
                "rows",
                "cols"
              ],
              "additionalProperties": false
            }
          },
          "additionalProperties": false
        }
      }
    },
    "required": true
  },
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "$ref": "#/components/schemas/Pty"
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "PtyNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/PtyNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### DELETE `/api/pty/{ptyID}`

Remove PTY session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "ptyID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^pty"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "PtyNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/PtyNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/pty/{ptyID}/connect`

Connect to PTY session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "ptyID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^pty"
      },
      "required": true
    },
    {
      "in": "query",
      "name": "location[directory]",
      "schema": {
        "type": "string"
      }
    },
    {
      "in": "query",
      "name": "location[workspace]",
      "schema": {
        "type": "string"
      }
    },
    {
      "in": "query",
      "name": "cursor",
      "schema": {
        "type": "string"
      }
    },
    {
      "in": "query",
      "name": "ticket",
      "schema": {
        "type": "string"
      }
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean"
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "403": {
      "description": "ForbiddenError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ForbiddenError"
          }
        }
      }
    },
    "404": {
      "description": "PtyNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/PtyNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/pty/{ptyID}/connect-token`

Create PTY WebSocket token

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "ptyID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^pty"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "$ref": "#/components/schemas/PtyTicketConnectToken"
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "403": {
      "description": "ForbiddenError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ForbiddenError"
          }
        }
      }
    },
    "404": {
      "description": "PtyNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/PtyNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/question/request`

List pending question requests

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/QuestionV2Request"
                }
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/reference`

List references

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/ReferenceInfo"
                }
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/session`

List sessions

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string",
        "pattern": "^wrk"
      },
      "required": false
    },
    {
      "name": "limit",
      "in": "query",
      "schema": {
        "type": "number"
      },
      "required": false
    },
    {
      "name": "order",
      "in": "query",
      "schema": {
        "type": "string",
        "enum": [
          "asc",
          "desc"
        ]
      },
      "required": false
    },
    {
      "name": "search",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "project",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "subpath",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "cursor",
      "in": "query",
      "schema": {
        "type": "string",
        "description": "Opaque pagination cursor returned as cursor.previous or cursor.next in the previous response."
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "SessionsResponse",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/SessionsResponse"
          }
        }
      }
    },
    "400": {
      "description": "InvalidCursorError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/InvalidCursorError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/session`

Create session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "id": {
              "type": "string",
              "pattern": "^ses"
            },
            "agent": {
              "type": "string"
            },
            "model": {
              "$ref": "#/components/schemas/ModelRef"
            },
            "location": {
              "$ref": "#/components/schemas/LocationRef"
            }
          },
          "additionalProperties": false
        }
      }
    },
    "required": true
  },
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "data": {
                "$ref": "#/components/schemas/SessionV2Info"
              }
            },
            "required": [
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/session/active`

List active sessions

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "data": {
                "type": "object",
                "patternProperties": {
                  "^ses": {
                    "$ref": "#/components/schemas/SessionActive"
                  }
                }
              }
            },
            "required": [
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/session/{sessionID}`

Get session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "data": {
                "$ref": "#/components/schemas/SessionV2Info"
              }
            },
            "required": [
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/session/{sessionID}/agent`

Switch session agent

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "agent": {
              "type": "string"
            }
          },
          "required": [
            "agent"
          ],
          "additionalProperties": false
        }
      }
    },
    "required": true
  },
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/session/{sessionID}/compact`

Compact session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    }
  ],
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    },
    "503": {
      "description": "ServiceUnavailableError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ServiceUnavailableError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/session/{sessionID}/context`

Get session context

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/SessionMessage"
                }
              }
            },
            "required": [
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    },
    "500": {
      "description": "UnknownError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnknownError1"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/session/{sessionID}/event`

Subscribe to session events

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "after",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "text/event-stream": {
          "schema": {
            "type": "object",
            "properties": {
              "id": {
                "type": "string"
              },
              "event": {
                "type": "string"
              },
              "data": {
                "$ref": "#/components/schemas/SessionDurableEventStream"
              }
            },
            "required": [
              "id",
              "event",
              "data"
            ],
            "additionalProperties": false
          },
          "x-effect-stream": {
            "encoding": "sse",
            "causeSchema": {
              "type": "array",
              "items": {
                "anyOf": [
                  {
                    "type": "object",
                    "properties": {
                      "_tag": {
                        "type": "string",
                        "enum": [
                          "Fail"
                        ]
                      },
                      "error": {
                        "not": {}
                      }
                    },
                    "required": [
                      "_tag",
                      "error"
                    ],
                    "additionalProperties": false
                  },
                  {
                    "type": "object",
                    "properties": {
                      "_tag": {
                        "type": "string",
                        "enum": [
                          "Die"
                        ]
                      },
                      "defect": {}
                    },
                    "required": [
                      "_tag",
                      "defect"
                    ],
                    "additionalProperties": false
                  },
                  {
                    "type": "object",
                    "properties": {
                      "_tag": {
                        "type": "string",
                        "enum": [
                          "Interrupt"
                        ]
                      },
                      "fiberId": {
                        "anyOf": [
                          {
                            "type": "number"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      }
                    },
                    "required": [
                      "_tag",
                      "fiberId"
                    ],
                    "additionalProperties": false
                  }
                ]
              }
            },
            "errorSchema": {
              "not": {}
            },
            "failureEvent": "effect/httpapi/stream/failure"
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/session/{sessionID}/history`

Get session history

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "limit",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "after",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "SessionHistory",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/SessionHistory"
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/session/{sessionID}/interrupt`

Interrupt session execution

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    }
  ],
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/session/{sessionID}/message`

Get session messages

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "limit",
      "in": "query",
      "schema": {
        "type": "number"
      },
      "required": false
    },
    {
      "name": "order",
      "in": "query",
      "schema": {
        "type": "string",
        "enum": [
          "asc",
          "desc"
        ]
      },
      "required": false
    },
    {
      "name": "cursor",
      "in": "query",
      "schema": {
        "type": "string",
        "description": "Opaque pagination cursor returned as cursor.previous or cursor.next in the previous response. Do not combine with order."
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "SessionMessagesResponse",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/SessionMessagesResponse"
          }
        }
      }
    },
    "400": {
      "description": "InvalidCursorError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/InvalidCursorError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    },
    "500": {
      "description": "UnknownError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnknownError1"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/session/{sessionID}/message/{messageID}`

Get session message

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "messageID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^msg_"
      },
      "required": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "data": {
                "$ref": "#/components/schemas/SessionMessage"
              }
            },
            "required": [
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError | MessageNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/MessageNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/session/{sessionID}/model`

Switch session model

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "model": {
              "$ref": "#/components/schemas/ModelRef"
            }
          },
          "required": [
            "model"
          ],
          "additionalProperties": false
        }
      }
    },
    "required": true
  },
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/session/{sessionID}/permission`

Create permission request

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "id": {
              "type": "string",
              "pattern": "^per"
            },
            "action": {
              "type": "string"
            },
            "resources": {
              "type": "array",
              "items": {
                "type": "string"
              }
            },
            "save": {
              "type": "array",
              "items": {
                "type": "string"
              }
            },
            "metadata": {
              "type": "object"
            },
            "source": {
              "$ref": "#/components/schemas/PermissionV2Source"
            },
            "agent": {
              "type": "string"
            }
          },
          "required": [
            "action",
            "resources"
          ],
          "additionalProperties": false
        }
      }
    },
    "required": true
  },
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "data": {
                "type": "object",
                "properties": {
                  "id": {
                    "type": "string",
                    "pattern": "^per"
                  },
                  "effect": {
                    "$ref": "#/components/schemas/PermissionV2Effect"
                  }
                },
                "required": [
                  "id",
                  "effect"
                ],
                "additionalProperties": false
              }
            },
            "required": [
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/session/{sessionID}/permission`

List session permission requests

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/PermissionV2Request"
                }
              }
            },
            "required": [
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/session/{sessionID}/permission/{requestID}`

Get permission request

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "requestID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^per"
      },
      "required": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "data": {
                "$ref": "#/components/schemas/PermissionV2Request"
              }
            },
            "required": [
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError | PermissionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/PermissionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/session/{sessionID}/permission/{requestID}/reply`

Reply to pending permission request

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "requestID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^per"
      },
      "required": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "reply": {
              "$ref": "#/components/schemas/PermissionV2Reply"
            },
            "message": {
              "type": "string"
            }
          },
          "required": [
            "reply"
          ],
          "additionalProperties": false
        }
      }
    },
    "required": true
  },
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError | PermissionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/PermissionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/session/{sessionID}/prompt`

Send message

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "id": {
              "type": "string",
              "pattern": "^msg_"
            },
            "prompt": {
              "$ref": "#/components/schemas/PromptInput"
            },
            "delivery": {
              "type": "string",
              "enum": [
                "steer",
                "queue"
              ]
            },
            "resume": {
              "type": "boolean"
            }
          },
          "required": [
            "prompt"
          ],
          "additionalProperties": false
        }
      }
    },
    "required": true
  },
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "data": {
                "$ref": "#/components/schemas/SessionInputAdmitted"
              }
            },
            "required": [
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    },
    "409": {
      "description": "ConflictError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ConflictError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/session/{sessionID}/question`

List session question requests

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/QuestionV2Request"
                }
              }
            },
            "required": [
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/session/{sessionID}/question/{requestID}/reject`

Reject pending question request

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "requestID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^que"
      },
      "required": true
    }
  ],
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError | QuestionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/QuestionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/session/{sessionID}/question/{requestID}/reply`

Reply to pending question request

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "requestID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^que"
      },
      "required": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/QuestionV2Reply"
        }
      }
    },
    "required": true
  },
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError | QuestionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/QuestionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/session/{sessionID}/revert/clear`

Clear staged revert

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    }
  ],
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    },
    "500": {
      "description": "UnknownError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnknownError1"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/session/{sessionID}/revert/commit`

Commit staged revert

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    }
  ],
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/session/{sessionID}/revert/stage`

Stage session revert

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "messageID": {
              "type": "string",
              "pattern": "^msg_"
            },
            "files": {
              "type": "boolean"
            }
          },
          "required": [
            "messageID"
          ],
          "additionalProperties": false
        }
      }
    },
    "required": true
  },
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "data": {
                "$ref": "#/components/schemas/RevertState"
              }
            },
            "required": [
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "MessageNotFoundError | SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/MessageNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    },
    "500": {
      "description": "UnknownError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnknownError1"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/api/session/{sessionID}/wait`

Wait for session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    }
  ],
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    },
    "404": {
      "description": "SessionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              },
              {
                "$ref": "#/components/schemas/SessionNotFoundError"
              }
            ]
          }
        }
      }
    },
    "503": {
      "description": "ServiceUnavailableError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ServiceUnavailableError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/api/skill`

List skills

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "location": {
                "$ref": "#/components/schemas/LocationInfo"
              },
              "data": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/SkillV2Info"
                }
              }
            },
            "required": [
              "location",
              "data"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/InvalidRequestError"
          }
        }
      }
    },
    "401": {
      "description": "UnauthorizedError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/UnauthorizedError"
          }
        }
      }
    }
  }
}
```

</details>

### PUT `/auth/{providerID}`

Set auth credentials

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "providerID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/Auth"
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Successfully set authentication credentials",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Successfully set authentication credentials"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### DELETE `/auth/{providerID}`

Remove auth credentials

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "providerID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    }
  ],
  "responses": {
    "200": {
      "description": "Successfully removed authentication credentials",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Successfully removed authentication credentials"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/command`

List commands

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "List of commands",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Command"
            },
            "description": "List of commands"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/config`

Get configuration

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Get config info",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Config"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### PATCH `/config`

Update configuration

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/Config"
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Successfully updated config",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Config"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/config/providers`

List config providers

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "List of providers",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "providers": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/Provider"
                }
              },
              "default": {
                "type": "object",
                "additionalProperties": {
                  "type": "string"
                }
              }
            },
            "required": [
              "providers",
              "default"
            ],
            "additionalProperties": false,
            "description": "List of providers"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/event`

Subscribe to events

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Event stream",
      "content": {
        "text/event-stream": {
          "schema": {
            "$ref": "#/components/schemas/Event"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/experimental/capabilities`

Get experimental capabilities

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Experimental capabilities",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ExperimentalCapabilities"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/experimental/console`

Get active Console provider metadata

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Active Console provider metadata",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ConsoleState"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    },
    "500": {
      "description": "InternalServerError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/effect_HttpApiError_InternalServerError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/experimental/console/orgs`

List switchable Console orgs

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Switchable Console orgs",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "orgs": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "accountID": {
                      "type": "string"
                    },
                    "accountEmail": {
                      "type": "string"
                    },
                    "accountUrl": {
                      "type": "string"
                    },
                    "orgID": {
                      "type": "string"
                    },
                    "orgName": {
                      "type": "string"
                    },
                    "active": {
                      "type": "boolean"
                    }
                  },
                  "required": [
                    "accountID",
                    "accountEmail",
                    "accountUrl",
                    "orgID",
                    "orgName",
                    "active"
                  ],
                  "additionalProperties": false
                }
              }
            },
            "required": [
              "orgs"
            ],
            "additionalProperties": false,
            "description": "Switchable Console orgs"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    },
    "500": {
      "description": "InternalServerError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/effect_HttpApiError_InternalServerError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/experimental/console/switch`

Switch active Console org

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "accountID": {
              "type": "string"
            },
            "orgID": {
              "type": "string"
            }
          },
          "required": [
            "accountID",
            "orgID"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Switch success",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Switch success"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/experimental/control-plane/move-session`

Move session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "sessionID": {
              "type": "string",
              "pattern": "^ses"
            },
            "destination": {
              "$ref": "#/components/schemas/MoveSessionDestination"
            },
            "moveChanges": {
              "type": "boolean"
            }
          },
          "required": [
            "sessionID",
            "destination"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "204": {
      "description": "Session moved"
    },
    "400": {
      "description": "MoveSessionError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/MoveSessionError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/experimental/project/{projectID}/copy`

v2.projectCopy.create

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "projectID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "strategy": {
              "type": "string"
            },
            "directory": {
              "type": "string"
            },
            "name": {
              "type": "string"
            }
          },
          "required": [
            "strategy",
            "directory"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "ProjectCopy.Copy",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ProjectCopyCopy"
          }
        }
      }
    },
    "400": {
      "description": "ProjectCopyError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ProjectCopyError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### DELETE `/experimental/project/{projectID}/copy`

v2.projectCopy.remove

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "projectID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "directory": {
              "type": "string"
            },
            "force": {
              "type": "boolean"
            }
          },
          "required": [
            "directory",
            "force"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "ProjectCopyError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ProjectCopyError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/experimental/project/{projectID}/copy/generate-name`

Generate project copy name

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "projectID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "context": {
              "type": "string"
            }
          },
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Success",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "name": {
                "type": "string"
              }
            },
            "required": [
              "name"
            ],
            "additionalProperties": false
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/experimental/project/{projectID}/copy/refresh`

v2.projectCopy.refresh

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "projectID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "location",
      "in": "query",
      "schema": {
        "type": "object",
        "properties": {
          "directory": {
            "type": "string"
          },
          "workspace": {
            "type": "string"
          }
        },
        "additionalProperties": false
      },
      "required": false,
      "style": "deepObject",
      "explode": true
    }
  ],
  "responses": {
    "204": {
      "description": "<No Content>"
    },
    "400": {
      "description": "ProjectCopyError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ProjectCopyError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/experimental/resource`

Get MCP resources

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "MCP resources",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "additionalProperties": {
              "$ref": "#/components/schemas/McpResource"
            },
            "description": "MCP resources"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/experimental/session`

List sessions

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "roots",
      "in": "query",
      "schema": {
        "anyOf": [
          {
            "type": "boolean"
          },
          {
            "type": "string",
            "enum": [
              "true",
              "false"
            ]
          }
        ]
      },
      "required": false
    },
    {
      "name": "start",
      "in": "query",
      "schema": {
        "type": "number"
      },
      "required": false
    },
    {
      "name": "cursor",
      "in": "query",
      "schema": {
        "type": "number"
      },
      "required": false
    },
    {
      "name": "search",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "limit",
      "in": "query",
      "schema": {
        "type": "number"
      },
      "required": false
    },
    {
      "name": "archived",
      "in": "query",
      "schema": {
        "anyOf": [
          {
            "type": "boolean"
          },
          {
            "type": "string",
            "enum": [
              "true",
              "false"
            ]
          }
        ]
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "List of sessions",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/GlobalSession"
            },
            "description": "List of sessions"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/experimental/session/{sessionID}/background`

Background subagents

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Backgrounded subagents",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Backgrounded subagents"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/experimental/tool`

List tools

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "provider",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "model",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": true
    }
  ],
  "responses": {
    "200": {
      "description": "Tools",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ToolList"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/experimental/tool/ids`

List tool IDs

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Tool IDs",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ToolIDs"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/experimental/workspace`

List workspaces

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Workspaces",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Workspace"
            },
            "description": "Workspaces"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/experimental/workspace`

Create workspace

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "id": {
              "type": "string",
              "pattern": "^wrk"
            },
            "type": {
              "type": "string"
            },
            "branch": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ]
            },
            "extra": {
              "anyOf": [
                {},
                {
                  "type": "null"
                }
              ]
            }
          },
          "required": [
            "type"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Workspace created",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Workspace"
          }
        }
      }
    },
    "400": {
      "description": "WorkspaceCreateError | BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/WorkspaceCreateError"
              },
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/experimental/workspace/adapter`

List workspace adapters

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Workspace adapters",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "type": {
                  "type": "string"
                },
                "name": {
                  "type": "string"
                },
                "description": {
                  "type": "string"
                }
              },
              "required": [
                "type",
                "name",
                "description"
              ],
              "additionalProperties": false
            },
            "description": "Workspace adapters"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/experimental/workspace/status`

Workspace status

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Workspace status",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/WorkspaceEventConnectionStatus"
            },
            "description": "Workspace status"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/experimental/workspace/sync-list`

Sync workspace list

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "204": {
      "description": "Workspace list synced"
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/experimental/workspace/warp`

Warp session into workspace

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "id": {
              "anyOf": [
                {
                  "type": "string",
                  "pattern": "^wrk"
                },
                {
                  "type": "null"
                }
              ]
            },
            "sessionID": {
              "type": "string",
              "pattern": "^ses"
            },
            "copyChanges": {
              "type": "boolean"
            }
          },
          "required": [
            "id",
            "sessionID"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "204": {
      "description": "Session warped"
    },
    "400": {
      "description": "WorkspaceWarpError | VcsApplyError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/WorkspaceWarpError"
              },
              {
                "$ref": "#/components/schemas/VcsApplyError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### DELETE `/experimental/workspace/{id}`

Remove workspace

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "id",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^wrk"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Workspace removed",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Workspace"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/experimental/worktree`

List worktrees

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "List of worktree directories",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "type": "string"
            },
            "description": "List of worktree directories"
          }
        }
      }
    },
    "400": {
      "description": "WorktreeError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/WorktreeError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/experimental/worktree`

Create worktree

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/WorktreeCreateInput"
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Worktree created",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Worktree"
          }
        }
      }
    },
    "400": {
      "description": "WorktreeError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/WorktreeError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### DELETE `/experimental/worktree`

Remove worktree

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/WorktreeRemoveInput"
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Worktree removed",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Worktree removed"
          }
        }
      }
    },
    "400": {
      "description": "WorktreeError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/WorktreeError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/experimental/worktree/reset`

Reset worktree

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/WorktreeResetInput"
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Worktree reset",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Worktree reset"
          }
        }
      }
    },
    "400": {
      "description": "WorktreeError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/WorktreeError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/file`

List files

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "path",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": true
    }
  ],
  "responses": {
    "200": {
      "description": "Files and directories",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/FileNode"
            },
            "description": "Files and directories"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/file/content`

Read file

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "path",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": true
    }
  ],
  "responses": {
    "200": {
      "description": "File content",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/FileContent"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/file/status`

Get file status

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "File status",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/File"
            },
            "description": "File status"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/find`

Find text

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "pattern",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": true
    }
  ],
  "responses": {
    "200": {
      "description": "Matches",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "path": {
                  "type": "object",
                  "properties": {
                    "text": {
                      "type": "string"
                    }
                  },
                  "required": [
                    "text"
                  ],
                  "additionalProperties": false
                },
                "lines": {
                  "type": "object",
                  "properties": {
                    "text": {
                      "type": "string"
                    }
                  },
                  "required": [
                    "text"
                  ],
                  "additionalProperties": false
                },
                "line_number": {
                  "type": "integer",
                  "minimum": 0
                },
                "absolute_offset": {
                  "type": "integer",
                  "minimum": 0
                },
                "submatches": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "match": {
                        "type": "object",
                        "properties": {
                          "text": {
                            "type": "string"
                          }
                        },
                        "required": [
                          "text"
                        ],
                        "additionalProperties": false
                      },
                      "start": {
                        "type": "integer",
                        "minimum": 0
                      },
                      "end": {
                        "type": "integer",
                        "minimum": 0
                      }
                    },
                    "required": [
                      "match",
                      "start",
                      "end"
                    ],
                    "additionalProperties": false
                  }
                }
              },
              "required": [
                "path",
                "lines",
                "line_number",
                "absolute_offset",
                "submatches"
              ],
              "additionalProperties": false
            },
            "description": "Matches"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/find/file`

Find files

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "query",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "dirs",
      "in": "query",
      "schema": {
        "type": "string",
        "enum": [
          "true",
          "false"
        ]
      },
      "required": false
    },
    {
      "name": "type",
      "in": "query",
      "schema": {
        "type": "string",
        "enum": [
          "file",
          "directory"
        ]
      },
      "required": false
    },
    {
      "name": "limit",
      "in": "query",
      "schema": {
        "type": "integer",
        "minimum": 1,
        "maximum": 200
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "File paths",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "type": "string"
            },
            "description": "File paths"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/find/symbol`

Find symbols

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "query",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": true
    }
  ],
  "responses": {
    "200": {
      "description": "Symbols",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Symbol"
            },
            "description": "Symbols"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/formatter`

Get formatter status

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Formatter status",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/FormatterStatus"
            },
            "description": "Formatter status"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/global/config`

Get global configuration

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [],
  "responses": {
    "200": {
      "description": "Get global config info",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Config"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### PATCH `/global/config`

Update global configuration

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/Config"
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Successfully updated global config",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Config"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/global/dispose`

Dispose instance

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [],
  "responses": {
    "200": {
      "description": "Global disposed",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Global disposed"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/global/event`

Get global events

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [],
  "responses": {
    "200": {
      "description": "Event stream",
      "content": {
        "text/event-stream": {
          "schema": {
            "$ref": "#/components/schemas/GlobalEvent"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/global/health`

Get health

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [],
  "responses": {
    "200": {
      "description": "Health information",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "healthy": {
                "type": "boolean",
                "enum": [
                  true
                ]
              },
              "version": {
                "type": "string"
              }
            },
            "required": [
              "healthy",
              "version"
            ],
            "additionalProperties": false,
            "description": "Health information"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/global/upgrade`

Upgrade opencode

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "target": {
              "type": "string"
            }
          },
          "required": [
            "target"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Upgrade result",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "type": "object",
                "properties": {
                  "success": {
                    "type": "boolean",
                    "enum": [
                      true
                    ]
                  },
                  "version": {
                    "type": "string"
                  }
                },
                "required": [
                  "success",
                  "version"
                ],
                "additionalProperties": false
              },
              {
                "type": "object",
                "properties": {
                  "success": {
                    "type": "boolean",
                    "enum": [
                      false
                    ]
                  },
                  "error": {
                    "type": "string"
                  }
                },
                "required": [
                  "success",
                  "error"
                ],
                "additionalProperties": false
              }
            ],
            "description": "Upgrade result"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/instance/dispose`

Dispose instance

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Instance disposed",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Instance disposed"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/log`

Write log

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "service": {
              "type": "string",
              "description": "Service name for the log entry"
            },
            "level": {
              "type": "string",
              "enum": [
                "debug",
                "info",
                "error",
                "warn"
              ],
              "description": "Log level"
            },
            "message": {
              "type": "string",
              "description": "Log message"
            },
            "extra": {
              "type": "object"
            }
          },
          "required": [
            "service",
            "level",
            "message"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Log entry written successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Log entry written successfully"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/lsp`

Get LSP status

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "LSP server status",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/LSPStatus"
            },
            "description": "LSP server status"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/mcp`

Get MCP status

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "MCP server status",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "additionalProperties": {
              "$ref": "#/components/schemas/MCPStatus"
            },
            "description": "MCP server status"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/mcp`

Add MCP server

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "name": {
              "type": "string"
            },
            "config": {
              "anyOf": [
                {
                  "$ref": "#/components/schemas/McpLocalConfig"
                },
                {
                  "$ref": "#/components/schemas/McpRemoteConfig"
                }
              ]
            }
          },
          "required": [
            "name",
            "config"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "MCP server added successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "additionalProperties": {
              "$ref": "#/components/schemas/MCPStatus"
            },
            "description": "MCP server added successfully"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/mcp/{name}/auth`

Start MCP OAuth

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "name",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "OAuth flow started",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "authorizationUrl": {
                "type": "string"
              },
              "oauthState": {
                "type": "string"
              }
            },
            "required": [
              "authorizationUrl",
              "oauthState"
            ],
            "additionalProperties": false,
            "description": "OAuth flow started"
          }
        }
      }
    },
    "400": {
      "description": "McpUnsupportedOAuthError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/McpUnsupportedOAuthError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "McpServerNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/McpServerNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### DELETE `/mcp/{name}/auth`

Remove MCP OAuth

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "name",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "OAuth credentials removed",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "success": {
                "type": "boolean",
                "enum": [
                  true
                ]
              }
            },
            "required": [
              "success"
            ],
            "additionalProperties": false,
            "description": "OAuth credentials removed"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    },
    "404": {
      "description": "McpServerNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/McpServerNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/mcp/{name}/auth/authenticate`

Authenticate MCP OAuth

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "name",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "OAuth authentication completed",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/MCPStatus"
          }
        }
      }
    },
    "400": {
      "description": "McpUnsupportedOAuthError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/McpUnsupportedOAuthError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "McpServerNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/McpServerNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/mcp/{name}/auth/callback`

Complete MCP OAuth

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "name",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "code": {
              "type": "string"
            }
          },
          "required": [
            "code"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "OAuth authentication completed",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/MCPStatus"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "McpServerNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/McpServerNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/mcp/{name}/connect`

mcp.connect

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "name",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "MCP server connected successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "MCP server connected successfully"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    },
    "404": {
      "description": "McpServerNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/McpServerNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/mcp/{name}/disconnect`

mcp.disconnect

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "name",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "MCP server disconnected successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "MCP server disconnected successfully"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    },
    "404": {
      "description": "McpServerNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/McpServerNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/path`

Get paths

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Path",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Path"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/permission`

List pending permissions

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "List of pending permissions",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/PermissionRequest"
            },
            "description": "List of pending permissions"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/permission/{requestID}/reply`

Respond to permission request

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "requestID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^per"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "reply": {
              "type": "string",
              "enum": [
                "once",
                "always",
                "reject"
              ]
            },
            "message": {
              "type": "string"
            }
          },
          "required": [
            "reply"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Permission processed successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Permission processed successfully"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "PermissionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/PermissionNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/project`

List all projects

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "List of projects",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Project"
            },
            "description": "List of projects"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/project/current`

Get current project

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Current project information",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Project"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/project/git/init`

Initialize git repository

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Project information after git initialization",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Project"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### PATCH `/project/{projectID}`

Update project

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "projectID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "name": {
              "type": "string"
            },
            "icon": {
              "$ref": "#/components/schemas/ProjectIcon"
            },
            "commands": {
              "$ref": "#/components/schemas/ProjectCommands"
            }
          },
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Updated project information",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Project"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "ProjectNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ProjectNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/project/{projectID}/directories`

List project directories

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "projectID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Project directories",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ProjectDirectories"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/provider`

List providers

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "List of providers",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "all": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/Provider"
                }
              },
              "default": {
                "type": "object",
                "additionalProperties": {
                  "type": "string"
                }
              },
              "connected": {
                "type": "array",
                "items": {
                  "type": "string"
                }
              }
            },
            "required": [
              "all",
              "default",
              "connected"
            ],
            "additionalProperties": false,
            "description": "List of providers"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/provider/auth`

Get provider auth methods

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Provider auth methods",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "additionalProperties": {
              "type": "array",
              "items": {
                "$ref": "#/components/schemas/ProviderAuthMethod"
              }
            },
            "description": "Provider auth methods"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/provider/{providerID}/oauth/authorize`

Start OAuth authorization

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "providerID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "method": {
              "type": "number",
              "description": "Auth method index"
            },
            "inputs": {
              "type": "object",
              "additionalProperties": {
                "type": "string"
              }
            }
          },
          "required": [
            "method"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Authorization URL and method",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/ProviderAuthAuthorization"
          }
        }
      }
    },
    "400": {
      "description": "ProviderAuthError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ProviderAuthError1"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/provider/{providerID}/oauth/callback`

Handle OAuth callback

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "providerID",
      "in": "path",
      "schema": {
        "type": "string"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "method": {
              "type": "number",
              "description": "Auth method index"
            },
            "code": {
              "type": "string"
            }
          },
          "required": [
            "method"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "OAuth callback processed successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "OAuth callback processed successfully"
          }
        }
      }
    },
    "400": {
      "description": "ProviderAuthError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ProviderAuthError1"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/pty`

List PTY sessions

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "List of sessions",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Pty"
            },
            "description": "List of sessions"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/pty`

Create PTY session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "command": {
              "type": "string"
            },
            "args": {
              "type": "array",
              "items": {
                "type": "string"
              }
            },
            "cwd": {
              "type": "string"
            },
            "title": {
              "type": "string"
            },
            "env": {
              "type": "object",
              "additionalProperties": {
                "type": "string"
              }
            }
          },
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Created session",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Pty"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/pty/shells`

List available shells

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "List of shells",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "path": {
                  "type": "string"
                },
                "name": {
                  "type": "string"
                },
                "acceptable": {
                  "type": "boolean"
                }
              },
              "required": [
                "path",
                "name",
                "acceptable"
              ],
              "additionalProperties": false
            },
            "description": "List of shells"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/pty/{ptyID}`

Get PTY session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "ptyID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^pty"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Session info",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Pty"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    },
    "404": {
      "description": "PtyNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/PtyNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### PUT `/pty/{ptyID}`

Update PTY session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "ptyID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^pty"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "title": {
              "type": "string"
            },
            "size": {
              "type": "object",
              "properties": {
                "rows": {
                  "type": "integer",
                  "exclusiveMinimum": 0
                },
                "cols": {
                  "type": "integer",
                  "exclusiveMinimum": 0
                }
              },
              "required": [
                "rows",
                "cols"
              ],
              "additionalProperties": false
            }
          },
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Updated session",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Pty"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "PtyNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/PtyNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### DELETE `/pty/{ptyID}`

Remove PTY session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "ptyID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^pty"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Session removed",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Session removed"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    },
    "404": {
      "description": "PtyNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/PtyNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/pty/{ptyID}/connect`

Connect to PTY session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "ptyID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^pty"
      },
      "required": true
    },
    {
      "in": "query",
      "name": "directory",
      "schema": {
        "type": "string"
      }
    },
    {
      "in": "query",
      "name": "workspace",
      "schema": {
        "type": "string"
      }
    },
    {
      "in": "query",
      "name": "cursor",
      "schema": {
        "type": "string"
      }
    },
    {
      "in": "query",
      "name": "ticket",
      "schema": {
        "type": "string"
      }
    }
  ],
  "responses": {
    "200": {
      "description": "Connected session",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Connected session"
          }
        }
      }
    },
    "403": {
      "description": "Forbidden",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/effect_HttpApiError_Forbidden"
          }
        }
      }
    },
    "404": {
      "description": "Not found",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/pty/{ptyID}/connect-token`

Create PTY WebSocket token

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "ptyID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^pty"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "WebSocket connect token",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/PtyTicketConnectToken"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    },
    "403": {
      "description": "PtyForbiddenError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/PtyForbiddenError"
          }
        }
      }
    },
    "404": {
      "description": "PtyNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/PtyNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/question`

List pending questions

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "List of pending questions",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/QuestionRequest"
            },
            "description": "List of pending questions"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/question/{requestID}/reject`

Reject question request

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "requestID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^que"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Question rejected successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Question rejected successfully"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "QuestionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/QuestionNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/question/{requestID}/reply`

Reply to question request

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "requestID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^que"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "answers": {
              "type": "array",
              "items": {
                "$ref": "#/components/schemas/QuestionAnswer"
              },
              "description": "User answers in order of questions (each answer is an array of selected labels)"
            }
          },
          "required": [
            "answers"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Question answered successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Question answered successfully"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "QuestionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/QuestionNotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/session`

List sessions

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "scope",
      "in": "query",
      "schema": {
        "type": "string",
        "enum": [
          "project"
        ]
      },
      "required": false
    },
    {
      "name": "path",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "roots",
      "in": "query",
      "schema": {
        "anyOf": [
          {
            "type": "boolean"
          },
          {
            "type": "string",
            "enum": [
              "true",
              "false"
            ]
          }
        ]
      },
      "required": false
    },
    {
      "name": "start",
      "in": "query",
      "schema": {
        "type": "number"
      },
      "required": false
    },
    {
      "name": "search",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "limit",
      "in": "query",
      "schema": {
        "type": "number"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "List of sessions",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Session"
            },
            "description": "List of sessions"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/session`

Create session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "parentID": {
              "type": "string",
              "pattern": "^ses"
            },
            "title": {
              "type": "string"
            },
            "agent": {
              "type": "string"
            },
            "model": {
              "type": "object",
              "properties": {
                "id": {
                  "type": "string"
                },
                "providerID": {
                  "type": "string"
                },
                "variant": {
                  "type": "string"
                }
              },
              "required": [
                "id",
                "providerID"
              ],
              "additionalProperties": false
            },
            "metadata": {
              "type": "object"
            },
            "permission": {
              "$ref": "#/components/schemas/PermissionRuleset"
            },
            "workspaceID": {
              "type": "string",
              "pattern": "^wrk"
            }
          },
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Successfully created session",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Session"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/session/status`

Get session status

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Get session status",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "additionalProperties": {
              "$ref": "#/components/schemas/SessionStatus"
            },
            "description": "Get session status"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/session/{sessionID}`

Get session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Get session",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Session"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### DELETE `/session/{sessionID}`

Delete session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Successfully deleted session",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Successfully deleted session"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### PATCH `/session/{sessionID}`

Update session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "title": {
              "type": "string"
            },
            "metadata": {
              "type": "object"
            },
            "permission": {
              "$ref": "#/components/schemas/PermissionRuleset"
            },
            "time": {
              "type": "object",
              "properties": {
                "archived": {
                  "type": "number"
                }
              },
              "additionalProperties": false
            }
          },
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Successfully updated session",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Session"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/session/{sessionID}/abort`

Abort session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Aborted session",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Aborted session"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/session/{sessionID}/children`

Get session children

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "List of children",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Session"
            },
            "description": "List of children"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/session/{sessionID}/command`

Send command

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "messageID": {
              "type": "string",
              "pattern": "^msg"
            },
            "agent": {
              "type": "string"
            },
            "model": {
              "type": "string"
            },
            "arguments": {
              "type": "string"
            },
            "command": {
              "type": "string"
            },
            "variant": {
              "type": "string"
            },
            "parts": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "id": {
                    "type": "string",
                    "pattern": "^prt"
                  },
                  "type": {
                    "type": "string",
                    "enum": [
                      "file"
                    ]
                  },
                  "mime": {
                    "type": "string"
                  },
                  "filename": {
                    "type": "string"
                  },
                  "url": {
                    "type": "string"
                  },
                  "source": {
                    "$ref": "#/components/schemas/FilePartSource"
                  }
                },
                "required": [
                  "type",
                  "mime",
                  "url"
                ],
                "additionalProperties": false
              }
            }
          },
          "required": [
            "arguments",
            "command"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Created message",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "required": [
              "info",
              "parts"
            ],
            "properties": {
              "info": {
                "$ref": "#/components/schemas/AssistantMessage"
              },
              "parts": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/Part"
                }
              }
            }
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/session/{sessionID}/diff`

Get message diff

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "messageID",
      "in": "query",
      "schema": {
        "type": "string",
        "pattern": "^msg"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Successfully retrieved diff",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/SnapshotFileDiff"
            },
            "description": "Successfully retrieved diff"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/session/{sessionID}/fork`

Fork session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "messageID": {
              "type": "string",
              "pattern": "^msg"
            }
          },
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "200",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Session"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/session/{sessionID}/init`

Initialize session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "modelID": {
              "type": "string"
            },
            "providerID": {
              "type": "string"
            },
            "messageID": {
              "type": "string",
              "pattern": "^msg"
            }
          },
          "required": [
            "modelID",
            "providerID",
            "messageID"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "200",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "200"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/session/{sessionID}/message`

Get session messages

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "limit",
      "in": "query",
      "schema": {
        "type": "integer",
        "minimum": 0,
        "maximum": 9007199254740991
      },
      "required": false
    },
    {
      "name": "before",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "List of messages",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "info": {
                  "$ref": "#/components/schemas/Message"
                },
                "parts": {
                  "type": "array",
                  "items": {
                    "$ref": "#/components/schemas/Part"
                  }
                }
              },
              "required": [
                "info",
                "parts"
              ],
              "additionalProperties": false
            },
            "description": "List of messages"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/session/{sessionID}/message`

Send message

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "messageID": {
              "type": "string",
              "pattern": "^msg"
            },
            "model": {
              "type": "object",
              "properties": {
                "providerID": {
                  "type": "string"
                },
                "modelID": {
                  "type": "string"
                }
              },
              "required": [
                "providerID",
                "modelID"
              ],
              "additionalProperties": false
            },
            "agent": {
              "type": "string"
            },
            "noReply": {
              "type": "boolean"
            },
            "tools": {
              "type": "object",
              "additionalProperties": {
                "type": "boolean"
              }
            },
            "format": {
              "$ref": "#/components/schemas/OutputFormat"
            },
            "system": {
              "type": "string"
            },
            "variant": {
              "type": "string"
            },
            "parts": {
              "type": "array",
              "items": {
                "anyOf": [
                  {
                    "$ref": "#/components/schemas/TextPartInput"
                  },
                  {
                    "$ref": "#/components/schemas/FilePartInput"
                  },
                  {
                    "$ref": "#/components/schemas/AgentPartInput"
                  },
                  {
                    "$ref": "#/components/schemas/SubtaskPartInput"
                  }
                ]
              }
            }
          },
          "required": [
            "parts"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Created message",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "required": [
              "info",
              "parts"
            ],
            "properties": {
              "info": {
                "$ref": "#/components/schemas/AssistantMessage"
              },
              "parts": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/Part"
                }
              }
            }
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/session/{sessionID}/message/{messageID}`

Get message

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "messageID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^msg"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Message",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "info": {
                "$ref": "#/components/schemas/Message"
              },
              "parts": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/Part"
                }
              }
            },
            "required": [
              "info",
              "parts"
            ],
            "additionalProperties": false,
            "description": "Message"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### DELETE `/session/{sessionID}/message/{messageID}`

Delete message

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "messageID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^msg"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Successfully deleted message",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Successfully deleted message"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    },
    "409": {
      "description": "SessionBusyError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/SessionBusyError"
          }
        }
      }
    }
  }
}
```

</details>

### DELETE `/session/{sessionID}/message/{messageID}/part/{partID}`

part.delete

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "messageID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^msg"
      },
      "required": true
    },
    {
      "name": "partID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^prt"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Successfully deleted part",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Successfully deleted part"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### PATCH `/session/{sessionID}/message/{messageID}/part/{partID}`

part.update

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "messageID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^msg"
      },
      "required": true
    },
    {
      "name": "partID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^prt"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/Part"
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Successfully updated part",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Part"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/session/{sessionID}/permissions/{permissionID}`

Respond to permission

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "permissionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^per"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "response": {
              "type": "string",
              "enum": [
                "once",
                "always",
                "reject"
              ]
            }
          },
          "required": [
            "response"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Permission processed successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Permission processed successfully"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError | PermissionNotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/NotFoundError"
              },
              {
                "$ref": "#/components/schemas/PermissionNotFoundError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/session/{sessionID}/prompt_async`

Send async message

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "messageID": {
              "type": "string",
              "pattern": "^msg"
            },
            "model": {
              "type": "object",
              "properties": {
                "providerID": {
                  "type": "string"
                },
                "modelID": {
                  "type": "string"
                }
              },
              "required": [
                "providerID",
                "modelID"
              ],
              "additionalProperties": false
            },
            "agent": {
              "type": "string"
            },
            "noReply": {
              "type": "boolean"
            },
            "tools": {
              "type": "object",
              "additionalProperties": {
                "type": "boolean"
              }
            },
            "format": {
              "$ref": "#/components/schemas/OutputFormat"
            },
            "system": {
              "type": "string"
            },
            "variant": {
              "type": "string"
            },
            "parts": {
              "type": "array",
              "items": {
                "anyOf": [
                  {
                    "$ref": "#/components/schemas/TextPartInput"
                  },
                  {
                    "$ref": "#/components/schemas/FilePartInput"
                  },
                  {
                    "$ref": "#/components/schemas/AgentPartInput"
                  },
                  {
                    "$ref": "#/components/schemas/SubtaskPartInput"
                  }
                ]
              }
            }
          },
          "required": [
            "parts"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "204": {
      "description": "Prompt accepted"
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/session/{sessionID}/revert`

Revert message

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "messageID": {
              "type": "string",
              "pattern": "^msg"
            },
            "partID": {
              "type": "string",
              "pattern": "^prt"
            }
          },
          "required": [
            "messageID"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Updated session",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Session"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    },
    "409": {
      "description": "SessionBusyError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/SessionBusyError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/session/{sessionID}/share`

Share session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Successfully shared session",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Session"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    },
    "500": {
      "description": "InternalServerError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/effect_HttpApiError_InternalServerError"
          }
        }
      }
    }
  }
}
```

</details>

### DELETE `/session/{sessionID}/share`

Unshare session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Successfully unshared session",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Session"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    },
    "500": {
      "description": "InternalServerError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/effect_HttpApiError_InternalServerError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/session/{sessionID}/shell`

Run shell command

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "messageID": {
              "type": "string",
              "pattern": "^msg"
            },
            "agent": {
              "type": "string"
            },
            "model": {
              "type": "object",
              "properties": {
                "providerID": {
                  "type": "string"
                },
                "modelID": {
                  "type": "string"
                }
              },
              "required": [
                "providerID",
                "modelID"
              ],
              "additionalProperties": false
            },
            "command": {
              "type": "string"
            }
          },
          "required": [
            "agent",
            "command"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Created message",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "info": {
                "$ref": "#/components/schemas/Message"
              },
              "parts": {
                "type": "array",
                "items": {
                  "$ref": "#/components/schemas/Part"
                }
              }
            },
            "required": [
              "info",
              "parts"
            ],
            "additionalProperties": false,
            "description": "Created message"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    },
    "409": {
      "description": "SessionBusyError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/SessionBusyError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/session/{sessionID}/summarize`

Summarize session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "providerID": {
              "type": "string"
            },
            "modelID": {
              "type": "string"
            },
            "auto": {
              "type": "boolean"
            }
          },
          "required": [
            "providerID",
            "modelID"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Summarized session",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Summarized session"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/session/{sessionID}/todo`

Get session todos

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Todo list",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/Todo"
            },
            "description": "Todo list"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/session/{sessionID}/unrevert`

Restore reverted messages

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "sessionID",
      "in": "path",
      "schema": {
        "type": "string",
        "pattern": "^ses"
      },
      "required": true
    },
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Updated session",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/Session"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    },
    "409": {
      "description": "SessionBusyError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/SessionBusyError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/skill`

List skills

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "List of skills",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "name": {
                  "type": "string"
                },
                "description": {
                  "type": "string"
                },
                "location": {
                  "type": "string"
                },
                "content": {
                  "type": "string"
                }
              },
              "required": [
                "name",
                "location",
                "content"
              ],
              "additionalProperties": false
            },
            "description": "List of skills"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/sync/history`

List sync events

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "additionalProperties": {
            "type": "integer",
            "minimum": 0
          }
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Sync events",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "id": {
                  "type": "string",
                  "pattern": "^evt_"
                },
                "aggregate_id": {
                  "type": "string"
                },
                "seq": {
                  "type": "integer",
                  "minimum": 0
                },
                "type": {
                  "type": "string"
                },
                "data": {
                  "type": "object"
                }
              },
              "required": [
                "id",
                "aggregate_id",
                "seq",
                "type",
                "data"
              ],
              "additionalProperties": false
            },
            "description": "Sync events"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/sync/replay`

Replay sync events

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "directory": {
              "type": "string"
            },
            "events": {
              "type": "array",
              "minItems": 1,
              "items": {
                "type": "object",
                "properties": {
                  "id": {
                    "type": "string",
                    "pattern": "^evt_"
                  },
                  "aggregateID": {
                    "type": "string"
                  },
                  "seq": {
                    "type": "integer",
                    "minimum": 0
                  },
                  "type": {
                    "type": "string"
                  },
                  "data": {
                    "type": "object"
                  }
                },
                "required": [
                  "id",
                  "aggregateID",
                  "seq",
                  "type",
                  "data"
                ],
                "additionalProperties": false
              }
            }
          },
          "required": [
            "directory",
            "events"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Replayed sync events",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "sessionID": {
                "type": "string"
              }
            },
            "required": [
              "sessionID"
            ],
            "additionalProperties": false,
            "description": "Replayed sync events"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/sync/start`

Start workspace sync

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Workspace sync started",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Workspace sync started"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/sync/steal`

Steal session into workspace

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "sessionID": {
              "type": "string",
              "pattern": "^ses"
            }
          },
          "required": [
            "sessionID"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Session stolen into workspace",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "sessionID": {
                "type": "string",
                "pattern": "^ses"
              }
            },
            "required": [
              "sessionID"
            ],
            "additionalProperties": false,
            "description": "Session stolen into workspace"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/tui/append-prompt`

Append TUI prompt

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "text": {
              "type": "string"
            }
          },
          "required": [
            "text"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Prompt processed successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Prompt processed successfully"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/tui/clear-prompt`

Clear TUI prompt

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Prompt cleared successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Prompt cleared successfully"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/tui/control/next`

Get next TUI request

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Next TUI request",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "path": {
                "type": "string"
              },
              "body": {}
            },
            "required": [
              "path",
              "body"
            ],
            "additionalProperties": false,
            "description": "Next TUI request"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/tui/control/response`

Submit TUI response

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {}
      }
    }
  },
  "responses": {
    "200": {
      "description": "Response submitted successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Response submitted successfully"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/tui/execute-command`

Execute TUI command

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "command": {
              "type": "string"
            }
          },
          "required": [
            "command"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Command executed successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Command executed successfully"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/tui/open-help`

Open help dialog

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Help dialog opened successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Help dialog opened successfully"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/tui/open-models`

Open models dialog

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Model dialog opened successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Model dialog opened successfully"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/tui/open-sessions`

Open sessions dialog

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Session dialog opened successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Session dialog opened successfully"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/tui/open-themes`

Open themes dialog

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Theme dialog opened successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Theme dialog opened successfully"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/tui/publish`

Publish TUI event

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "anyOf": [
            {
              "$ref": "#/components/schemas/EventTuiPromptAppend"
            },
            {
              "$ref": "#/components/schemas/EventTuiCommandExecute"
            },
            {
              "$ref": "#/components/schemas/EventTuiToastShow"
            },
            {
              "$ref": "#/components/schemas/EventTuiSessionSelect"
            }
          ]
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Event published successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Event published successfully"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### POST `/tui/select-session`

Select session

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "sessionID": {
              "type": "string",
              "pattern": "^ses",
              "description": "Session ID to navigate to"
            }
          },
          "required": [
            "sessionID"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Session selected successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Session selected successfully"
          }
        }
      }
    },
    "400": {
      "description": "BadRequest | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/effect_HttpApiError_BadRequest"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    },
    "404": {
      "description": "NotFoundError",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/NotFoundError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/tui/show-toast`

Show TUI toast

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "title": {
              "type": "string"
            },
            "message": {
              "type": "string"
            },
            "variant": {
              "type": "string",
              "enum": [
                "info",
                "success",
                "warning",
                "error"
              ]
            },
            "duration": {
              "type": "integer",
              "exclusiveMinimum": 0
            }
          },
          "required": [
            "message",
            "variant"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "Toast notification shown successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Toast notification shown successfully"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/tui/submit-prompt`

Submit TUI prompt

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Prompt submitted successfully",
      "content": {
        "application/json": {
          "schema": {
            "type": "boolean",
            "description": "Prompt submitted successfully"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/vcs`

Get VCS info

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "VCS info",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/VcsInfo"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### POST `/vcs/apply`

Apply VCS patch

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "schema": {
          "type": "object",
          "properties": {
            "patch": {
              "type": "string"
            }
          },
          "required": [
            "patch"
          ],
          "additionalProperties": false
        }
      }
    }
  },
  "responses": {
    "200": {
      "description": "VCS patch applied",
      "content": {
        "application/json": {
          "schema": {
            "type": "object",
            "properties": {
              "applied": {
                "type": "boolean"
              }
            },
            "required": [
              "applied"
            ],
            "additionalProperties": false,
            "description": "VCS patch applied"
          }
        }
      }
    },
    "400": {
      "description": "VcsApplyError | InvalidRequestError",
      "content": {
        "application/json": {
          "schema": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/VcsApplyError"
              },
              {
                "$ref": "#/components/schemas/InvalidRequestError"
              }
            ]
          }
        }
      }
    }
  }
}
```

</details>

### GET `/vcs/diff`

Get VCS diff

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "mode",
      "in": "query",
      "schema": {
        "type": "string",
        "enum": [
          "git",
          "branch"
        ]
      },
      "required": true
    },
    {
      "name": "context",
      "in": "query",
      "schema": {
        "type": "integer",
        "minimum": 0
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "VCS diff",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/VcsFileDiff"
            },
            "description": "VCS diff"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/vcs/diff/raw`

Get raw VCS diff

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "Raw VCS diff",
      "content": {
        "text/x-diff; charset=utf-8": {
          "schema": {
            "type": "string"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

### GET `/vcs/status`

Get VCS status

<details><summary>参数、Body 和响应结构</summary>

```json
{
  "parameters": [
    {
      "name": "directory",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    },
    {
      "name": "workspace",
      "in": "query",
      "schema": {
        "type": "string"
      },
      "required": false
    }
  ],
  "responses": {
    "200": {
      "description": "VCS status",
      "content": {
        "application/json": {
          "schema": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/VcsFileStatus"
            },
            "description": "VCS status"
          }
        }
      }
    },
    "400": {
      "description": "Bad request",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/BadRequestError"
          }
        }
      }
    }
  }
}
```

</details>

平台业务操作共 78 项（另列网关/推理入口）；原生协议操作 188 项。
