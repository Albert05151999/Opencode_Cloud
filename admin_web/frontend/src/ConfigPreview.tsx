import { ModelPreview } from "./ModelPreview";
import { useEffect, useState } from "react";
import { Copy, Code2 } from "lucide-react";
import { Dict, remote } from "./api";

export function maskConfig(value: any): any {
  if (Array.isArray(value)) return value.map(maskConfig);
  if (value && typeof value === "object")
    return Object.fromEntries(
      Object.entries(value).map(([k, v]) => [
        k,
        /^(api_?key|headers|extra_headers|environment|authorization|password|secret|token|sources)$/i.test(
          k,
        )
          ? v
            ? "••••"
            : v
          : maskConfig(v),
      ]),
    );
  return value;
}
export function JsonConfig({
  title,
  value,
  note,
}: {
  title: string;
  value: any;
  note?: string;
}) {
  const [copied, setCopied] = useState(false),
    [error, setError] = useState("");
  const text = JSON.stringify(maskConfig(value), null, 2);
  useEffect(() => setCopied(false), [text]);
  return (
    <section className="config-json">
      <div className="section-heading">
        <h3>
          <Code2 size={16} /> {title}
        </h3>
        <button
          type="button"
          className="text-button"
          aria-label={"复制 " + title}
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(text);
              setCopied(true);
              setError("");
            } catch {
              setError("复制失败，请选择下方 JSON 手动复制");
            }
          }}
        >
          <Copy size={14} />
          {copied ? "已复制" : "复制 JSON"}
        </button>
      </div>
      {note && <p className="muted">{note}</p>}
      {error && <p role="alert">{error}</p>}
      <pre className="json-view">{text}</pre>
    </section>
  );
}

export function ConfigurationView({ value }: { value: Dict }) {
  if (typeof value.ok === 'boolean') return <section aria-label="测试结果">
    <div className={`notice ${value.ok ? 'success' : 'error'}`} role={value.ok ? 'status' : 'alert'}>
      <strong>{value.ok ? '连接测试通过' : '连接测试失败'}</strong>
      <p>{value.ok ? '服务器已完成测试请求。测试不会保存或发布配置。' : String(value.error || value.detail || '请检查地址、凭据和模型配置后重试。')}</p>
    </div>
    <details><summary>查看诊断数据</summary><pre className="json-view">{JSON.stringify(maskConfig(value), null, 2)}</pre></details>
  </section>;
  if (value.scope === "resource-library")
    return (
      <>
        <p className="notice">
          全局是资源库，不会直接作为一个 opencode.json 加载。模型通过 LiteLLM
          网关调用，MCP、Skills、Hook 需在 Agent 中绑定后才生效。
        </p>
        <JsonConfig title="全局模型资源库 · 已保存" value={value.models} />
        <JsonConfig title="全局扩展资源库 · 已保存" value={value.resources} />
        <JsonConfig
          title={
            value.gateway_applying
              ? "模型网关 · 发布中"
              : "模型网关 · 已生效 v" + (value.gateway_version ?? "—")
          }
          value={value.active_gateway}
          note="这是 LiteLLM 配置，不是 Agent 的 opencode.json。凭据已隐藏。"
        />
      </>
    );
  if ("active_opencode" in value)
    return (
      <>
        <JsonConfig
          title={"opencode.json · 已生效 v" + (value.active_version ?? "—")}
          value={value.active_opencode}
          note={
            value.active_opencode
              ? "读取服务器当前发布版本的配置文件。"
              : "尚无已发布的配置文件。"
          }
        />
        <JsonConfig
          title="opencode.json · 已保存草稿"
          value={value.draft_opencode}
          note="按当前草稿编译，发布前不会改变运行中的配置。"
        />
        <JsonConfig title="资源来源与版本" value={value.resources} />
      </>
    );
  return (
    <pre className="json-view">
      {JSON.stringify(maskConfig(value), null, 2)}
    </pre>
  );
}

export function FormConfigPreview({
  type,
  value,
  parameters,
}: {
  type: string;
  value: Dict;
  parameters: string;
}) {
  const [result, setResult] = useState<Dict | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  useEffect(() => {
    if (type !== "agent") return;
    let cancelled = false;
    setLoading(true);
    setResult(null);
    setError("");
    if (
      !value.name ||
      !value.allowed_model_ids?.length ||
      !value.default_model_id
    ) {
      setLoading(false);
      setError("请填写 Agent 名称、选择至少一个模型并设置默认模型。");
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const { id, ...config } = value;
        const r = await remote(
          `/cloud/admin/agents/${encodeURIComponent(id || "preview-agent")}/config-preview`,
          "POST",
          { config },
        );
        if (!cancelled) setResult(r);
      } catch (e: any) {
        if (!cancelled) setError(e.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [type, value]);
  if (type === "agent")
    return (
      <div className="form-config-preview">
        <h3>表单 → opencode.json</h3>
        <p className="muted">
          实时调用服务器发布编译器，仅预览，不保存或启动沙箱。
        </p>
        {loading && <p role="status">正在生成预览…</p>}
        {error && <p className="notice warning">请完善表单后预览：{error}</p>}
        {result && (
          <JsonConfig title="沙箱资源 · 当前表单（未保存）" value={result.resources} note="cpu_limit 为核数，memory_mb 为 MiB；继承默认值时显示服务器实际配置。" />
        )}
        {result && (
          <JsonConfig
            title="opencode.json · 当前表单（未保存）"
            value={result.opencode}
          />
        )}
      </div>
    );
  let fragment: Dict = {},
    note = "此片段在资源发布、绑定到 Agent 并发布 Agent 后插入配置。";
  if (type === "model")
    return <ModelPreview value={value} parameters={parameters} />;

  const data = value.data || {},
    name = value.name || value.id || "<资源名称>";
  if (value.kind === "mcp") {
    const { cwd, ...native } = data;
    if (native.type === "local" && cwd)
      native.command = [
        "python3",
        "-c",
        "import os,sys; os.chdir(sys.argv[1]); os.execvp(sys.argv[2],sys.argv[2:])",
        cwd,
        ...(native.command || []),
      ];
    fragment = { mcp: { [name]: native } };
  } else if (value.kind === "hook") {
    const entry = data.compiled_entry || data.entry;
    fragment = {
      plugin: [
        `file:///opt/agent/plugins/${value.id || "<资源ID>"}/${entry || "hook.mjs"}`,
      ],
    };
    note =
      "这是待绑定路径示意；TS 入口以服务器发布后的编译结果为准。最终数组保留系统 trace Hook，并按 Agent 的 Hook 顺序生成。";
  } else {
    fragment = { skills: { paths: ["/opt/agent/skills"] } };
    note = `附件由服务器校验后安装到 /opt/agent/skills/${value.id || "<资源ID>"}/，保留文件结构。绑定资源后由原生 Skill 发现机制加载。`;
  }
  return (
    <div className="form-config-preview">
      <JsonConfig
        title="opencode.json 插入片段 · 当前表单"
        value={fragment}
        note={note}
      />
    </div>
  );
}
