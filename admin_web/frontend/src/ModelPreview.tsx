import { useEffect, useState } from "react";
import { Dict, remote } from "./api";
import { JsonConfig } from "./ConfigPreview";

export function ModelPreview({
  value,
  parameters,
}: {
  value: Dict;
  parameters: string;
}) {
  const [result, setResult] = useState<Dict | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setResult(null);
    setError("");
    const timer = setTimeout(async () => {
      try {
        const { references, ...model } = value;
        const data = await remote(
          "/cloud/admin/models/config-preview",
          "POST",
          { model: { ...model, parameters: JSON.parse(parameters) } },
        );
        if (active) setResult(data);
      } catch (e: any) {
        if (active) setError(e.message);
      }
    }, 350);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [value, parameters]);
  return (
    <section className="form-config-preview">
      <p className="muted">
        以下条目由服务器网关编译器生成；仅预览，不保存。模型需发布网关并分配给
        Agent 后才能使用。
      </p>
      {error && <p className="notice warning">请完善模型表单后预览：{error}</p>}
      {result && (
        <>
          <h3>实际映射</h3>
          <p><code>cloud-model-gateway/{value.id}</code> → <code>model_name: {value.id}</code> → {result.gateway.length} 个启用部署</p>
          <div className="table-scroll"><table><thead><tr><th>部署 ID</th><th>上游模型</th><th>地址</th><th>RPM / TPM / 权重</th></tr></thead>
            <tbody>{result.gateway.map((entry: Dict) => <tr key={entry.model_info.id}>
              <td>{entry.model_info.id}</td><td>{entry.litellm_params.model}</td><td>{entry.litellm_params.api_base || '协议默认地址'}</td>
              <td>{entry.litellm_params.rpm || '—'} / {entry.litellm_params.tpm || '—'} / {entry.litellm_params.weight || '—'}</td>
            </tr>)}</tbody></table></div>
          <JsonConfig title="负载均衡策略" value={result.router_settings} />
          <JsonConfig title="模型网关条目 · 当前表单" value={result.gateway} />
          <JsonConfig
            title="Agent 选择此模型后的 opencode.json 片段"
            value={result.agent}
          />
        </>
      )}
    </section>
  );
}
