import { waitForPublish } from "./publishing";
import "./operations-design.css";
import { RefreshCw, Layers, GitBranch, Send } from "lucide-react";
import { useEffect, useState } from "react";
import { Dict, remote, download } from "./api";

export function AgentTemplates({ onChanged }: { onChanged: () => void }) {
  const [templates, setTemplates] = useState<Dict[]>([]),
    [selected, setSelected] = useState<Dict | null>(null),
    [catalog, setCatalog] = useState<Dict | null>(null),
    [models, setModels] = useState<Dict>({}),
    [resources, setResources] = useState<Dict>({}),
    [id, setId] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  async function reload() {
    try {
      const [items, data] = await Promise.all([
        remote("/cloud/admin/agent-templates"),
        remote("/cloud/admin/catalog?compact=true"),
      ]);
      setTemplates(Array.isArray(items) ? items : []);
      setCatalog(data);
    } catch (e: any) {
      setMessage(e.message);
    }
  }
  useEffect(() => {
    void reload();
  }, []);
  async function job(path: string) {
    const j = await remote(path, "POST", {});
    await waitForPublish(j.job_id);
  }

  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    try {
      await fn();
      await reload();
      onChanged();
    } catch (e: any) {
      setMessage(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel ops-design ops-panel ops-templates">
      <div className="section-heading"><h3>发布、分配与待恢复模板</h3>
      <button onClick={reload}><RefreshCw size={16} aria-hidden="true" />刷新资源与模板</button></div>
      <p>
        先发布模型网关和扩展资源，再选择对应版本恢复 Agent 草稿。恢复不覆盖已有
        Agent，也不会自动发布。
      </p>
      {message && <p role="status">{message}</p>}
      <section className="ops-step-section"><h4><Layers size={18} aria-hidden="true" /> 发布模型与资源</h4>
      {catalog && (
        <>
          <button
            disabled={busy}
            onClick={() =>
              act(async () => {
                await job("/cloud/admin/models/apply");
                setMessage("模型网关已发布");
              })
            }
          >
            发布模型网关
          </button>
          {Object.values(catalog.resources || {}).map((r: any) => (
            <div className="actions ops-resource-action" key={r.id}>
              <span>
                {r.name} · {r.id} · 已发布 {r.versions.length} 个版本
              </span>
              <button
                disabled={busy}
                onClick={() =>
                  act(async () => {
                    const result = await remote(
                      `/cloud/admin/resources/${r.id}/publish`,
                      "POST",
                      { agent_id: Object.keys(catalog.agents)[0] },
                    );
                    if (result.job_id) {
                      await waitForPublish(result.job_id);
                    }
                    setMessage("资源发布完成");
                  })
                }
              >
                校验并发布此资源
              </button>
            </div>
          ))}
        </>
      )}
      </section>
      <section className="ops-step-section"><h4><GitBranch size={18} aria-hidden="true" /> 从模板恢复草稿</h4>
      {!templates.length && <p className="ops-empty-inline">尚无待恢复模板。导入包含 Agent 模板的资源包后，可在这里映射模型与资源版本。</p>}
      <label>
        待恢复配置
        <select
          value={selected?.id || ""}
          onChange={(e) => {
            setSelected(templates.find((t) => t.id === e.target.value) || null);
            setModels({});
            setResources({});
            setId("");
          }}
        >
          <option value="">选择模板</option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name || t.source_id}
            </option>
          ))}
        </select>
      </label>
      {selected && catalog && (
        <>
          <label>
            新的 Agent ID
            <input value={id} onChange={(e) => setId(e.target.value)} />
          </label>
          {selected.config.allowed_model_ids.map((mid: string) => (
            <label key={mid}>
              模型 {mid}
              <select
                value={models[mid] || mid}
                onChange={(e) =>
                  setModels({ ...models, [mid]: e.target.value })
                }
              >
                <option value={mid}>{mid}</option>
                {Object.values(catalog.models)
                  .filter((m: any) => m.enabled !== false && m.id !== mid)
                  .map((m: any) => (
                    <option key={m.id} value={m.id}>
                      {m.name || m.id}
                    </option>
                  ))}
              </select>
            </label>
          ))}
          {selected.config.bindings.map((b: Dict) => (
            <label key={b.id}>
              资源 {b.id}
              <select
                value={
                  resources[b.id]
                    ? `${resources[b.id].id}:${resources[b.id].version}`
                    : `${b.id}:1`
                }
                onChange={(e) => {
                  const [rid, v] = e.target.value.split(":");
                  setResources({
                    ...resources,
                    [b.id]: { id: rid, version: Number(v) },
                  });
                }}
              >
                <option value={`${b.id}:1`}>{b.id} v1（需要先发布）</option>
                {Object.values(catalog.resources).flatMap((r: any) =>
                  r.versions.map((v: any) => (
                    <option
                      key={`${r.id}:${v.version}`}
                      value={`${r.id}:${v.version}`}
                    >
                      {r.name} / {r.id} v{v.version}
                    </option>
                  )),
                )}
              </select>
            </label>
          ))}
          <button
            disabled={busy || !id}
            onClick={() =>
              act(async () => {
                await remote(
                  `/cloud/admin/agent-templates/${selected.id}/restore`,
                  "POST",
                  { agent_id: id, models, resources },
                );
                setMessage("Agent 草稿已创建；请单独发布");
              })
            }
          >
            恢复为新的 Agent 草稿
          </button>
        </>
      )}
      </section>
      <section className="ops-step-section"><h4><Send size={18} aria-hidden="true" /> 发布与导出 Agent</h4>
      {catalog &&
        Object.values(catalog.agents).map((a: any) => (
          <div className="actions ops-agent-action" key={a.id}>
            <span>
              {a.draft.name} · {a.id}
            </span>
            <button
              disabled={busy}
              onClick={() =>
                act(async () => {
                  await job(`/cloud/admin/agents/${a.id}/apply`);
                  setMessage("Agent 已发布");
                })
              }
            >
              发布 Agent
            </button>
            <button
              disabled={busy}
              onClick={() =>
                act(async () => {
                  await download(
                    `/cloud/admin/exports/native/${a.id}`,
                    "opencode-native.zip",
                  );
                })
              }
            >
              导出原生 OpenCode 包
            </button>
          </div>
        ))}
      </section>
    </section>
  );
}
