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
