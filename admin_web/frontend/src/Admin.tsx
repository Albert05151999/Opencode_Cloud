import { currentAdminTab, navigateTo } from "./navigation";
import { waitForPublish } from "./publishing";
import { Observability } from "./Observability";
import { LoadTests } from "./LoadTests";
import { JobHistory } from "./JobHistory";
import { Capability } from "./Capability";
import { DeleteAgent } from "./DeleteAgent";
import { ProviderFields } from "./ProviderFields";
import { ModelDeployments, PasteModel } from './ModelDeployments';
import { ResourceTransfer } from "./ResourceTransfer";
import { Operations } from "./Operations";
import { ConfigurationView, FormConfigPreview } from "./ConfigPreview";
import { useEffect, useState, useId, useRef, cloneElement } from "react";
import {
  Plus,
  RefreshCw,
  ArrowUpRight,
  Check,
  Upload,
  Search,
  ChevronRight,
  X,
  ArrowUp,
  ArrowDown,
  Settings2,
  Box,
  Code2,
  BookOpen,
  Network,
  Layers,
  History,
  Copy,
  Activity,
  Gauge,
  ArrowLeftRight,
} from "lucide-react";
import { bootstrap, request, remote, Dict, download } from "./api";

const tabs = [
  ["logs", "日志与调用链"],
  ["load-tests", "压测"],
  ["transfer", "导入导出"],
  ["sandboxes", "沙箱"],
  ["models", "模型"],
  ["agents", "Agents"],
  ["mcp", "MCP"],
  ["skill", "Skills"],
  ["hook", "Hook"],
  ["jobs", "发布记录"],
  ["connection", "连接设置"],
];
const emptyAgent = (id = "") => ({
  id,
  name: id,
  description: "",
  enabled: true,
  instructions: "You are a helpful coding assistant.",
  allowed_model_ids: [],
  default_model_id: "",
  small_model_id: null,
  cpu_limit: null,
  memory_mb: null,
  bindings: [],
});
export function Admin({
  boot,
  onConnection,
}: {
  boot: Dict;
  onConnection: (v: Dict) => void;
}) {
  const [showArchived, setShowArchived] = useState(false);
  const [deletingResource, setDeletingResource] = useState<string | null>(null);
  const [tab, setTabState] = useState(currentAdminTab),
    [catalog, setCatalog] = useState<Dict>({
      models: {},
      agents: {},
      resources: {},
      jobs: {},
    }),
    [error, setError] = useState(""),
    [success, setSuccess] = useState(""),
    [loading, setLoading] = useState(false),
    [publishing, setPublishing] = useState(false),
    [editor, setEditor] = useState<Dict | null>(null),
    [preview, setPreview] = useState<Dict | null>(null),
    [importing, setImporting] = useState(false);
  const setTab = (value: string) => navigateTo(`/admin?tab=${value}`);
  useEffect(() => {
    document.querySelector('.admin-tabs button.active')?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }, [tab]);
  useEffect(() => {
    const update = () => setTabState(currentAdminTab());
    window.addEventListener('popstate', update);
    return () => window.removeEventListener('popstate', update);
  }, []);
  const actionPending = useRef(false);
  const catalogSequence = useRef(0);
  const catalogPending = useRef(false);
  const reload = async () => {
    const sequence = ++catalogSequence.current;
    catalogPending.current = true;
    try {
      const c = await remote("/cloud/admin/catalog?compact=true");
      if (sequence !== catalogSequence.current) return;
      setCatalog(c);
      setError("");
    } catch (e: any) {
      if (sequence !== catalogSequence.current) return;
      setError(e.message);
      if (e.message.includes("credential") || e.message.includes("not found"))
        setTab("connection");
    } finally { if (sequence === catalogSequence.current) catalogPending.current = false; }
  };
  useEffect(() => {
    setCatalog({ models: {}, agents: {}, resources: {}, jobs: {} });
    void reload();
    return () => { ++catalogSequence.current; };
  }, [boot.url, boot.credential_configured]);
  useEffect(() => {
    if (
      tab === "jobs" ||
      !Object.values(catalog.jobs).some((j: any) =>
        ["queued", "running", "validating", "waiting", "applying"].includes(j.status),
      )
    )
      return;
    const timer = setInterval(() => { if (!document.hidden && !catalogPending.current) void reload(); }, 2500);
    return () => clearInterval(timer);
  }, [catalog.jobs, tab]);
  async function action(fn: () => Promise<any>, message = "操作完成") {
    if (actionPending.current) throw Error("已有操作正在执行，请等待完成后再试。");
    actionPending.current = true;
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      const result = await fn();
      if (result?.job_id) {
        setPublishing(true);
        await waitForPublish(result.job_id);
        setSuccess("发布成功，配置已生效");
      } else if (result?.ok === false) setError(String(result.error || result.detail || "测试失败，请查看诊断结果"));
      else setSuccess(message);
      await reload();
      return result;
    } catch (e: any) {
      setError(e.message);
      throw e;
    } finally {
      actionPending.current = false;
      setPublishing(false);
      setLoading(false);
    }
  }
  const safe = (fn: () => Promise<any>, message?: string) =>
    action(fn, message).catch(() => {});
  const entries =
    tab === "models"
      ? Object.values(catalog.models)
      : tab === "agents"
        ? Object.values(catalog.agents).filter(
            (a: any) =>
              showArchived || !["archived", "deleting"].includes(a.lifecycle),
          )
        : Object.values(catalog.resources).filter((r: any) => r.kind === tab && (showArchived || (!r.archived && r.id !== deletingResource)));
  const openNew = () =>
    setEditor(
      tab === "models"
        ? {
            type: "model",
            value: {
              id: "",
              name: "",
              provider: "openai-compatible",
              upstream_model: "",
              base_url: "",
              api_key: "",
              headers: {},
              parameters: {},
              enabled: true,
            },
          }
        : tab === "agents"
          ? { type: "agent", value: emptyAgent() }
          : {
              type: "resource",
              value: {
                id: "",
                kind: tab,
                name: "",
                owner: null,
                archived: false,
                data:
                  tab === "mcp"
                    ? {
                        type: "remote",
                        url: "",
                        headers: {},
                        timeout: 10000,
                        enabled: true,
                        oauth: false,
                      }
                    : tab === "hook"
                      ? {
                          entry: "hook.mjs",
                          sources: {
                            "hook.mjs":
                              'export default async () => ({\n  "tool.execute.before": async (input, output) => {\n    // Add your hook here.\n  }\n});\n',
                          },
                        }
                      : {},
              },
            },
    );
  async function saveEditor(value: Dict, file?: File) {
    if (!editor) return;
    await action(async () => {
      if (editor.type === "model") {
        const { id, references, ...rest } = value;
        if (!editor.existing && catalog.models[id]) throw Error("模型 ID 已存在，请改用其他 ID，或关闭表单后编辑已有模型。");
        return remote(`/cloud/admin/models/${encodeURIComponent(id)}`, "PUT", {
          model: { id, ...rest },
          revision: catalog.revision,
        });
      }
      if (editor.type === "agent") {
        const { id, ...config } = value;
        if (!editor.existing && catalog.agents[id]) throw Error("Agent ID 已存在，请改用其他 ID，或编辑已有 Agent。");
        return remote(`/cloud/admin/agents/${encodeURIComponent(id)}`, "PUT", {
          config,
          revision: catalog.revision,
        });
      }
      if (!editor.existing && catalog.resources[value.id]) throw Error("资源 ID 已存在，请使用其他 ID，或关闭表单后编辑已有资源。");
      if (value.kind === "skill" && file) {
        const form = new FormData();
        form.set("file", file);
        form.set("owner", value.owner || "");
        form.set("revision", String(catalog.revision));
        return remote(
          `/cloud/admin/resources/${encodeURIComponent(value.id)}/upload`,
          "POST",
          form,
        );
      }
      return remote(
        `/cloud/admin/resources/${encodeURIComponent(value.id)}`,
        "PUT",
        { resource: value, revision: catalog.revision },
      );
    }, "草稿已保存到服务器；发布后才生效");
    setEditor(null);
  }
  async function copyResource(r: Dict) {
    const owner = prompt("复制到哪个 Agent？输入已有 Agent ID");
    if (!owner) return;
    if (!catalog.agents[owner]) throw Error("Agent 不存在");
    const id = prompt("新资源 ID");
    if (!id) return;
    return remote(`/cloud/admin/resources/${r.id}/copy`, "POST", {
      id,
      owner,
      revision: catalog.revision,
    });
  }
  async function publishResource(r: Dict) {
    const target = r.owner || Object.keys(catalog.agents)[0];
    return remote(`/cloud/admin/resources/${r.id}/publish`, "POST", {
      agent_id: target,
    });
  }
  return (
    <div className="admin">
      <div className="admin-heading">
        <div>
          <p className="eyebrow">WORKSPACE CONTROL</p>
          <h1>运维控制台</h1>
          <p className="muted">观测请求、管理资源，让每一次运行都有据可查。</p>
        </div>
        <button
          className="secondary"
          onClick={() =>
            safe(async () => {
              const result = await remote("/cloud/admin/config-preview");
              setPreview(result);
              return result;
            })
          }
        >
          全局 JSON
        </button>
        <button className="secondary" onClick={reload}>
          <RefreshCw size={15} />
          刷新
        </button>
      </div>
      <div className="admin-tabs">
        {tabs.map(([id, title]) => (
          <button
            key={id}
            aria-label={title}
            className={tab === id ? "active" : ""}
            onClick={() => {
              setTab(id);
              setSuccess("");
            }}
          >
            {id === "logs" ? <Activity size={15}/> : id === "load-tests" ? <Gauge size={15}/> : id === "transfer" ? <ArrowLeftRight size={15}/> : id === "sandboxes" ? <Box size={15}/> : id === "models" ? <Layers size={15}/> : id === "agents" ? <Code2 size={15}/> : id === "jobs" ? <History size={15}/> : id === "connection" ? <Settings2 size={15}/> : <Network size={15}/>}
            {title}
          </button>
        ))}
      </div>
      {publishing && <div className="notice" role="status">已提交，正在等待发布结果。可在发布记录查看进度；配置尚未确认生效。</div>}
      {error && (
        <div className="notice error" role="alert">
          {error}
          {/Publish selected models|请先发布模型/.test(error)
            ? <button onClick={() => {setError(""); setTab("models");}}>配置并发布模型网关</button>
            : /凭据|credential|连接|connection|401|403/i.test(error)
              ? <button onClick={() => setTab("connection")}>检查连接</button>
              : <button onClick={() => setTab("jobs")}>查看发布记录</button>}
        </div>
      )}
      {success && (
        <div className="notice success" role="status">
          <Check size={16} />
          {success}
        </div>
      )}
      {tab === "logs" ? (
        <Observability />
      ) : tab === "load-tests" ? (
        <Capability name="load_testing">
          <LoadTests />
        </Capability>
      ) : tab === "transfer" ? (
        <Capability name="resource_transfer">
          <ResourceTransfer
            onChanged={() => {
              void reload();
            }}
          />
        </Capability>
      ) : tab === "sandboxes" ? (
        <Capability name="sandbox_operations">
          <Operations />
        </Capability>
      ) : tab === "connection" ? (
        <Connection boot={boot} onSaved={onConnection} run={safe} busy={loading} />
      ) : tab === "jobs" ? (
        <div className="panel">
          <div className="section-heading">
            <h2>发布与恢复</h2>
            <span className="muted">配置更新不会强制中止正在运行的任务</span>
          </div>
          <Capability name="sandbox_operations">
            <JobHistory />
          </Capability>
          <h3>模型网关版本</h3>
          {(catalog.gateway_versions || []).map((v: Dict) => (
            <div className="resource-row" key={v.version}>
              <span>
                版本 {v.version}
                {catalog.gateway_active === v.version ? " · 当前生效" : ""}
              </span>
              <button
                className="secondary"
                disabled={loading || v.version === catalog.gateway_active}
                onClick={() => {
                  if (confirm(`将模型网关恢复到 v${v.version}？请确认该版本的配置适用于当前 Agent。`)) void safe(
                    () => remote("/cloud/admin/models/apply", "POST", { version: v.version }), "已提交回滚");
                }}
              >
                恢复此版本
              </button>
            </div>
          ))}
        </div>
      ) : (
        <>
          <div className="section-heading">
            <div>
              <h2>
                {tabs.find((t) => t[0] === tab)?.[1]}{" "}
                <span className="count">{entries.length}</span>
              </h2>
              <p className="muted">
                {tab === "models"
                  ? "模型在全局保存，需显式分配给 Agent。"
                  : tab === "agents"
                    ? "每个 Agent 拥有独立的模型选择和资源版本。"
                    : "资源发布新版本，不会自动更新已经绑定的 Agent。"}
              </p>
            </div>
            <div className="actions">
              {["agents", "mcp", "skill", "hook"].includes(tab) && (
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={showArchived}
                    onChange={(e) => setShowArchived(e.target.checked)}
                  />
                  显示归档与删除中 {tab === "agents" ? "Agent" : tab === "skill" ? "Skill" : tab.toUpperCase()}
                </label>
              )}
              {tab === "models" && (
                <>
                  {(["minimax", "glm"] as const).map(id => <button key={id} className="secondary" onClick={() => setEditor({type: "model", value: {
                    id, name: id === "minimax" ? "MiniMax" : "GLM", provider: "openai-compatible",
                    upstream_model: id === "minimax" ? "MiniMax-M3" : "glm-5.3",
                    base_url: id === "minimax" ? "https://api.minimaxi.com/v1" : "https://api.z.ai/api/coding/paas/v4",
                    api_key: "", enabled: true, parameters: {}, headers: {},
                  }})}>使用 {id === "minimax" ? "MiniMax" : "GLM"} 示例</button>)}
                  {Object.values(catalog.models).some((m: any) => m.legacy) && (
                    <div className="notice warning">默认模型尚未配置。请在服务器执行模型导入，或编辑模型填写上游账户；保存后发布模型网关，再启用并发布 Agent。</div>
                  )}
                  <button
                    className="secondary"
                    onClick={() => setImporting(true)}
                  >
                    <Upload size={16} />
                    从本机导入
                  </button>
                  <button
                    className="secondary"
                    disabled={loading}
                    onClick={() =>
                      safe(() =>
                        remote("/cloud/admin/models/apply", "POST", {
                          revision: catalog.revision,
                        }),
                      )
                    }
                  >
                    发布模型网关
                  </button>
                </>
              )}
              <button className="primary" onClick={openNew}>
                <Plus size={16} />
                {tab === "skill" ? "上传 Skill" : "新建"}
              </button>
            </div>
          </div>
          <div className={tab === "agents" ? "agent-grid" : "panel"}>
            {entries.map((entry: any) =>
              tab === "agents" ? (
                <div className="agent-card" key={entry.id}>
                  <div className="agent-card-top">
                    <span className="agent-icon">
                      <SparkIcon />
                    </span>
                    <span
                      className={"badge " + (entry.active ? "succeeded" : "")}
                    >
                      {entry.active ? `生效 v${entry.active}` : "未发布"}
                    </span>
                  </div>
                  <h3>{entry.draft.name}</h3>
                  {["archived", "deleting"].includes(entry.lifecycle) && (
                    <DeleteAgent
                      id={entry.id}
                      onChanged={() => {
                        void reload();
                      }}
                    />
                  )}
                  <div className="actions">
                    <span className="badge">
                      {entry.lifecycle === "deleting"
                        ? "删除中"
                        : entry.lifecycle === "archived"
                          ? "已归档"
                          : "正常"}
                    </span>
                    <button
                      className="text-button"
                      disabled={loading || entry.lifecycle === "deleting"}
                      onClick={() => {
                        const operation =
                          entry.lifecycle === "archived"
                            ? "restore"
                            : "archive";
                        if (
                          confirm(
                            operation === "archive"
                              ? "归档后禁止新生成，保留历史和文件。确认？"
                              : "恢复此 Agent？",
                          )
                        )
                          void safe(() =>
                            remote(
                              `/cloud/admin/agents/${encodeURIComponent(entry.id)}/${operation}`,
                              "POST",
                              { request_id: crypto.randomUUID() },
                            ),
                          );
                      }}
                    >
                      {entry.lifecycle === "archived" ? "恢复" : "归档"}
                    </button>
                    {!entry.versions.length && (
                      <button
                        className="text-button"
                        disabled={loading}
                        onClick={() => {
                          if (
                            confirm(
                              "删除未发布的空 Agent？已有关联资源时服务器会拒绝删除。",
                            )
                          )
                            void safe(() =>
                              remote(
                                `/cloud/admin/agents/${encodeURIComponent(entry.id)}/delete-empty`,
                                "POST",
                                { request_id: crypto.randomUUID() },
                              ),
                            );
                        }}
                      >
                        删除空 Agent
                      </button>
                    )}
                  </div>
                  <p className="muted">{entry.id}</p>
                  <p>
                    {entry.draft.description ||
                      "为你的任务配置专属模型与工具。"}
                  </p>
                  <div className="chips">
                    <span>{entry.draft.allowed_model_ids.length} 个模型</span>
                    <span>{entry.draft.bindings.length} 项扩展</span>
                    {!entry.draft.enabled && <span>停用草稿</span>}
                  </div>
                  <div className="actions">
                    <button
                      className="secondary"
                      onClick={() =>
                        setEditor({
                          type: "agent",
                          existing: true,
                          value: { id: entry.id, ...entry.draft },
                        })
                      }
                    >
                      配置 Agent
                      <ChevronRight size={14} />
                    </button>
                    <button
                      className="icon"
                      title="复制 Agent"
                      onClick={() => {
                        const id = prompt("新 Agent ID（字母、数字、横线）");
                        if (id)
                          safe(() =>
                            remote(
                              `/cloud/admin/agents/${entry.id}/copy`,
                              "POST",
                              { id, revision: catalog.revision },
                            ),
                          );
                      }}
                    >
                      <Copy size={16} />
                    </button>
                    <button
                      className="text-button"
                      disabled={loading}
                      onClick={() =>
                        safe(() =>
                          remote(
                            `/cloud/admin/agents/${entry.id}/apply`,
                            "POST",
                            { revision: catalog.revision },
                          ),
                        )
                      }
                    >
                      发布
                    </button>
                  </div>
                  <button
                    className="text-button muted"
                    onClick={() =>
                      safe(async () => {
                        setPreview(
                          await remote(
                            `/cloud/admin/agents/${entry.id}/effective-config`,
                          ),
                        );
                        return {};
                      }, "预览已加载")
                    }
                  >
                    配置预览与版本历史
                  </button>
                </div>
              ) : (
                <div className="resource-row" key={entry.id}>
                  <span className={"resource-icon " + tab}>
                    {tab === "models" ? (
                      <Box size={21} />
                    ) : tab === "mcp" ? (
                      <Network size={21} />
                    ) : tab === "skill" ? (
                      <BookOpen size={21} />
                    ) : (
                      <Code2 size={21} />
                    )}
                  </span>
                  <div className="grow">
                    <strong>{entry.name || entry.id}</strong>
                    <p className="muted">
                      {entry.id} ·{" "}
                      {tab === "models"
                        ? entry.provider
                        : entry.owner
                          ? `私有 · ${entry.owner}`
                          : "全局资源库"}
                    </p>
                    {tab === 'models' && !entry.legacy && <p className="muted model-mapping-summary">
                      <code>cloud-model-gateway/{entry.id}</code> → {entry.upstream_model} · {entry.deployments?.length
                        ? entry.deployments.filter((d: Dict) => d.enabled !== false).length
                        : 1 + (entry.additional_base_urls?.length || 0)} 个启用部署
                    </p>}
                  </div>
                  <span className="badge">
                    {tab === "models"
                      ? entry.enabled === false
                        ? "已停用"
                        : entry.legacy
                          ? "已有模型"
                          : "候选配置"
                      : entry.id === deletingResource ? "删除中…" : entry.archived
                        ? "已归档"
                        : entry.versions.length
                          ? `v${entry.versions.length}`
                          : "草稿"}
                  </span>
                  <div className="actions">
                    {tab === "models" ? (
                      <button
                        className="text-button"
                        disabled={loading}
                        onClick={() =>
                          safe(
                            () =>
                              remote(
                                `/cloud/admin/models/${entry.id}/test`,
                                "POST",
                              ),
                            "测试请求已完成；失败原因请查看结果",
                          ).then((result) => {
                            if (result) setPreview(result);
                          })
                        }
                      >
                        测试
                      </button>
                    ) : (
                      <>
                        <button className="text-button" disabled={loading} onClick={()=>safe(()=>remote(`/cloud/admin/resources/${entry.id}/${entry.archived?'restore':'archive'}`,'POST',{revision:catalog.revision}),entry.archived?'资源已恢复':'资源已归档')}>{entry.archived?'恢复':'归档'}</button>
                        {entry.archived&&<button className="text-button" disabled={loading} onClick={()=>{
                          if(!confirm(`永久删除资源 ${entry.name||entry.id}？草稿、历史版本或模板仍有引用时不能删除。`))return;
                          setDeletingResource(entry.id);
                          void safe(()=>remote(`/cloud/admin/resources/${entry.id}?revision=${catalog.revision}`,'DELETE'),'资源已删除').finally(()=>setDeletingResource(null));
                        }}>永久删除</button>}
                        <button
                          className="text-button"
                          disabled={loading || entry.archived}
                          onClick={() =>
                            safe(() => publishResource(entry), "资源版本已发布")
                          }
                        >
                          发布
                        </button>
                        <button
                          className="text-button"
                          onClick={() =>
                            safe(async () => {
                              setPreview(
                                await remote(
                                  `/cloud/admin/resources/${entry.id}/versions`,
                                ),
                              );
                              return {};
                            }, "版本详情已加载")
                          }
                        >
                          版本
                        </button>
                        {tab === "mcp" && (
                          <button
                            className="text-button"
                            disabled={loading}
                            onClick={() => {
                              const aid =
                                entry.owner ||
                                prompt(
                                  "用于连接测试的 Agent ID",
                                  Object.keys(catalog.agents)[0],
                                );
                              if (aid)
                                safe(async () => {
                                  const r = await remote(
                                    `/cloud/admin/resources/${entry.id}/test`,
                                    "POST",
                                    { agent_id: aid },
                                  );
                                  setPreview(r);
                                  return r;
                                }, "连接测试完成");
                            }}
                          >
                            测试
                          </button>
                        )}
                      </>
                    )}
                    <button
                      className="text-button"
                      onClick={() => {
                        if (tab === "models")
                          setPreview({
                            model: entry.id,
                            references: entry.references || [],
                          });
                        else void safe(() => copyResource(entry));
                      }}
                    >
                      {tab === "models" ? "引用关系" : "复制为私有"}
                    </button>
                    <button
                      className="secondary"
                      onClick={() =>
                        setEditor(
                          tab === "models"
                            ? { type: "model", existing: true, value: entry }
                            : {
                                type: "resource",
                                existing: true,
                                value: { ...entry, data: entry.draft.data },
                              },
                        )
                      }
                    >
                      编辑
                    </button>
                  </div>
                </div>
              ),
            )}
            {!entries.length && (
              <Empty
                title="从第一个配置开始"
                text="资源通过公开接口保存在服务器，按版本分配给 Agent。"
              />
            )}
          </div>
        </>
      )}
      {editor && (
        <Editor
          key={editor.value.id + editor.type}
          editor={editor}
          catalog={catalog}
          busy={loading}
          onClose={() => setEditor(null)}
          onSave={saveEditor}
          onPrivate={(kind, owner) =>
            setEditor({
              type: "resource",
              value: {
                id: "",
                name: "",
                kind,
                owner,
                data:
                  kind === "mcp"
                    ? {
                        type: "remote",
                        url: "",
                        headers: {},
                        enabled: true,
                        timeout: 10000,
                      }
                    : kind === "hook"
                      ? {
                          entry: "hook.mjs",
                          sources: {
                            "hook.mjs": "export default async () => ({});",
                          },
                        }
                      : {},
              },
            })
          }
        />
      )}
      {preview && (
        <div className="modal-backdrop">
          <section className="modal" role="dialog" aria-modal="true" aria-label="配置与诊断">
            <div className="section-heading">
              <h2>配置与诊断</h2>
              <button className="icon" aria-label="关闭诊断" onClick={() => setPreview(null)}>
                <X />
              </button>
            </div>
            {preview.active_version !== undefined && (
              <div className="actions">
                {(catalog.agents[preview.agent_id]?.versions || []).map(
                  (v: Dict) => (
                    <button
                      className="secondary"
                      key={v.version}
                      disabled={loading || v.version === preview.active_version}
                      onClick={() => {
                        if (!confirm(`将 Agent ${preview.agent_id} 恢复到 v${v.version}？这会重新发布该历史配置。`)) return;
                        const a = catalog.agents[preview.agent_id] as Dict;
                        if (a)
                          safe(() =>
                            remote(
                              `/cloud/admin/agents/${a.id}/rollback`,
                              "POST",
                              { version: v.version },
                            ),
                          );
                      }}
                    >
                      恢复 v{v.version}
                    </button>
                  ),
                )}
              </div>
            )}
            <ConfigurationView value={preview} />
            {preview.kind === "skill" && (
              <div>
                {Object.keys(preview.draft.files).map((path) => (
                  <button
                    className="file-row"
                    key={path}
                    onClick={() => void download(
                        `/cloud/admin/resources/${preview.id}/file?path=${encodeURIComponent(path)}`,
                        path.split("/").pop()!,
                      ).catch(e => setError(e.message))}
                  >
                    {path}
                    <ArrowUpRight size={14} />
                  </button>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
      {importing && (
        <ImportModal
          revision={catalog.revision}
          onClose={() => setImporting(false)}
          onDone={async () => {
            setImporting(false);
            await reload();
            setSuccess("模型已导入。先发布模型网关，再到 Agent 页面分配。");
          }}
        />
      )}
    </div>
  );
}
function SparkIcon() {
  return <Layers size={22} />;
}
function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Layers />
      </span>
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {cloneElement(children as React.ReactElement<any>, {
        id,
        "aria-label": label,
      })}
    </div>
  );
}
function KeyValues({
  label,
  value,
  onChange,
}: {
  label: string;
  value: Dict;
  onChange: (v: Dict) => void;
}) {
  const [rows, setRows] = useState<[string, string][]>(
    Object.entries(value || {}),
  );
  const change = (next: [string, string][]) => {
    setRows(next);
    onChange(Object.fromEntries(next.filter(([k]) => k)));
  };
  return (
    <div className="field">
      <span>{label}</span>
      {rows.map(([k, v], i) => (
        <div className="kv-row" key={i}>
          <input
            aria-label={label + "名称"}
            placeholder="名称"
            value={k}
            onChange={(e) =>
              change(rows.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))
            }
          />
          <input
            aria-label={label + "值"}
            placeholder="值 / 保留 •••• 表示不修改"
            type="password"
            value={v}
            onChange={(e) =>
              change(rows.map((r, j) => (j === i ? [r[0], e.target.value] : r)))
            }
          />
          <button
            type="button"
            className="icon"
            onClick={() => change(rows.filter((_, j) => j !== i))}
          >
            <X size={15} />
          </button>
        </div>
      ))}
      <button
        type="button"
        className="text-button"
        onClick={() => change([...rows, ["", ""]])}
      >
        ＋ 添加一项
      </button>
    </div>
  );
}
function Editor({
  editor,
  catalog,
  busy,
  onClose,
  onSave,
  onPrivate,
}: {
  editor: Dict;
  catalog: Dict;
  busy: boolean;
  onClose: () => void;
  onSave: (v: Dict, f?: File) => Promise<void>;
  onPrivate: (kind: string, owner: string) => void;
}) {
  const [v, setV] = useState<Dict>(structuredClone(editor.value)),
    [error, setError] = useState(""),
    [file, setFile] = useState<File>(),
    [parameters, setParameters] = useState(
      JSON.stringify(editor.value.parameters || {}, null, 2),
    );
  const formRef = useRef<HTMLFormElement>(null);
  const dirty = JSON.stringify(v) !== JSON.stringify(editor.value) || !!file || parameters !== JSON.stringify(editor.value.parameters || {}, null, 2);
  const close = () => { if (!busy && (!dirty || confirm('放弃未保存的表单修改？'))) onClose(); };
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    formRef.current?.querySelector<HTMLElement>('input:not(:disabled), select, textarea, button')?.focus();
    return () => previous?.focus();
  }, []);
  useEffect(() => {
    const beforeUnload = (e: BeforeUnloadEvent) => { if (dirty || busy) { e.preventDefault(); e.returnValue = ''; } };
    const beforeNavigate = (e: Event) => {
      if (busy || (dirty && !confirm('放弃未保存的表单修改？'))) e.preventDefault();
      else onClose();
    };
    window.addEventListener('beforeunload', beforeUnload);
    window.addEventListener('app-before-navigate', beforeNavigate);
    return () => { window.removeEventListener('beforeunload', beforeUnload); window.removeEventListener('app-before-navigate', beforeNavigate); };
  }, [dirty, busy, onClose]);
  const update = (key: string, value: any) =>
    setV((old) => ({ ...old, [key]: value }));
  const data = (key: string, value: any) =>
    setV((old) => ({ ...old, data: { ...old.data, [key]: value } }));
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      let value = { ...v };
      if (editor.type === "model") value.parameters = JSON.parse(parameters);
      await onSave(value, file);
    } catch (e: any) {
      setError(e.message);
    }
  };
  const addBinding = (r: Dict, checked: boolean) =>
    update(
      "bindings",
      checked
        ? [...v.bindings, { id: r.id, version: r.versions.length }]
        : v.bindings.filter((b: Dict) => b.id !== r.id),
    );
  return (
    <div className="modal-backdrop">
      <form ref={formRef} onKeyDown={e => {
        if (e.key === 'Escape') { e.preventDefault(); close(); }
        if (e.key === 'Tab') {
          const items = Array.from(formRef.current!.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]')).filter(el => el.getClientRects().length);
          const first = items[0], last = items[items.length - 1];
          if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
          else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
        }
      }} className="modal editor" role="dialog" aria-modal="true" aria-labelledby="configuration-editor-title" onSubmit={submit}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">
              {editor.existing ? "EDIT CONFIGURATION" : "NEW CONFIGURATION"}
            </p>
            <h2 id="configuration-editor-title">
              {editor.type === "agent"
                ? "Agent 配置"
                : editor.type === "model"
                  ? "模型配置"
                  : v.kind === "hook"
                    ? "Hook 编辑器"
                    : v.kind === "skill"
                      ? "上传 Skill"
                      : "MCP 配置"}
            </h2>
          </div>
          <button type="button" className="icon" aria-label="关闭编辑器" onClick={close} disabled={busy}>
            <X />
          </button>
        </div>
        {error && <div className="notice error">{error}</div>}
        <div className="form-grid">
          <Field label="稳定 ID">
            <input
              required
              pattern="[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}"
              disabled={editor.existing}
              value={v.id}
              onChange={(e) => update("id", e.target.value)}
            />
          </Field>
          <Field
            label={
              editor.type === "resource"
                ? "名称（字母、数字、横线）"
                : "显示名称"
            }
          >
            <input
              required={v.kind !== "skill"}
              value={v.name || ""}
              onChange={(e) => update("name", e.target.value)}
            />
          </Field>
        </div>
        {editor.type === "model" && (
          <>
            <PasteModel onApply={(model) => {
              setV({ ...model, id: editor.existing ? v.id : model.id, legacy: false });
              setParameters(JSON.stringify(model.parameters || {}, null, 2));
            }} />
            <div className="form-grid">
              <Field label="提供商协议">
                <select
                  value={v.provider}
                  disabled={v.legacy}
                  onChange={(e) => update("provider", e.target.value)}
                >
                  {[
                    "openai-compatible",
                    "openai",
                    "anthropic",
                    "google",
                    ...(v.legacy ? ["legacy"] : []),
                  ].map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
              </Field>
              <Field label="上游模型 ID">
                <input
                  required
                  value={v.upstream_model}
                  onChange={(e) => update("upstream_model", e.target.value)}
                />
              </Field>
            </div>
            <Field label="Base URL">
              <input
                placeholder="https://api.example.com/v1"
                value={v.base_url || ""}
                onChange={(e) => update("base_url", e.target.value)}
              />
            </Field>
            {!v.deployments?.length && <>
            <Field label="其他等价端点（每行一个，共用 API key）">
              <textarea
                value={(v.additional_base_urls || []).join("\n")}
                onChange={(e) =>
                  update("additional_base_urls", e.target.value.split("\n"))
                }
                onBlur={(e) =>
                  update(
                    "additional_base_urls",
                    e.target.value
                      .split("\n")
                      .map((v) => v.trim())
                      .filter(Boolean),
                  )
                }
              />
            </Field>
            <Field label="API key">
              <input
                type="password"
                autoComplete="off"
                value={v.api_key || ""}
                onChange={(e) => update("api_key", e.target.value)}
              />
            </Field>
            </>}
            <ModelDeployments value={v} parameters={parameters} onChange={setV} />
            <KeyValues
              label="请求 headers"
              value={v.headers}
              onChange={(x) => update("headers", x)}
            />
            <div className="form-grid">
              <Field label="上下文 token 上限">
                <input
                  type="number"
                  min="1"
                  value={v.context || ""}
                  onChange={(e) =>
                    update(
                      "context",
                      e.target.value ? Number(e.target.value) : undefined,
                    )
                  }
                />
              </Field>
              <Field label="输出 token 上限">
                <input
                  type="number"
                  min="1"
                  value={v.output || ""}
                  onChange={(e) =>
                    update(
                      "output",
                      e.target.value ? Number(e.target.value) : undefined,
                    )
                  }
                />
              </Field>
            </div>
            <Field label="模型参数（JSON）">
              <textarea
                className="code-editor"
                value={parameters}
                onChange={(e) => setParameters(e.target.value)}
              />
            </Field>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={v.enabled !== false}
                onChange={(e) => update("enabled", e.target.checked)}
              />
              启用模型
            </label>
            {v.legacy && (
              <p className="muted">
                已有模型仍使用部署环境中的提供商配置。转换为可编辑模型前请通过导入替换该定义。
              </p>
            )}
          </>
        )}
        {editor.type === "agent" && (
          <>
            <Field label="说明">
              <input
                value={v.description}
                onChange={(e) => update("description", e.target.value)}
              />
            </Field>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={v.enabled}
                onChange={(e) => update("enabled", e.target.checked)}
              />
              启用 Agent（发布后生效）
            </label>
            <h3>沙箱资源</h3>
            <div className="form-grid">
              <Field label="CPU（核）">
                <select value={v.cpu_limit ?? ""} onChange={(e) => update("cpu_limit", e.target.value ? Number(e.target.value) : null)}>
                  <option value="">沿用服务器默认值</option>
                  {[1, 2, 4, 8].map((n) => <option key={n} value={n}>{n} 核</option>)}
                </select>
              </Field>
              <Field label="内存（GiB）">
                <select value={v.memory_mb ?? ""} onChange={(e) => update("memory_mb", e.target.value ? Number(e.target.value) : null)}>
                  <option value="">沿用服务器默认值</option>
                  {[1, 2, 4, 8].map((n) => <option key={n} value={n * 1024}>{n} GiB</option>)}
                </select>
              </Field>
            </div>
            <p className="muted">限制适用于该 Agent 的每个沙箱。保存草稿后需发布生效，发布会重建现有沙箱。工作目录映射到服务器，不设置容器磁盘容量限制。</p>
            <Field label="Agent 指令 · AGENTS.md">
              <textarea
                className="code-editor"
                value={v.instructions}
                onChange={(e) => update("instructions", e.target.value)}
              />
            </Field>
            <h3>选择可用模型</h3>
            <div className="choice-list">
              {Object.values(catalog.models).map((m: any) => (
                <label className="checkbox" key={m.id}>
                  <input
                    type="checkbox"
                    disabled={m.enabled === false}
                    checked={v.allowed_model_ids.includes(m.id)}
                    onChange={(e) =>
                      update(
                        "allowed_model_ids",
                        e.target.checked
                          ? [...v.allowed_model_ids, m.id]
                          : v.allowed_model_ids.filter(
                              (x: string) => x !== m.id,
                            ),
                      )
                    }
                  />
                  {m.name || m.id}
                  <span className="muted">{m.id}</span>
                </label>
              ))}
            </div>
            <div className="form-grid">
              <Field label="默认模型">
                <select
                  required
                  value={v.default_model_id}
                  onChange={(e) => update("default_model_id", e.target.value)}
                >
                  <option value="">请选择</option>
                  {v.allowed_model_ids.map((id: string) => (
                    <option key={id}>{id}</option>
                  ))}
                </select>
              </Field>
              <Field label="小模型（可选）">
                <select
                  value={v.small_model_id || ""}
                  onChange={(e) =>
                    update("small_model_id", e.target.value || null)
                  }
                >
                  <option value="">不指定</option>
                  {v.allowed_model_ids.map((id: string) => (
                    <option key={id}>{id}</option>
                  ))}
                </select>
              </Field>
            </div>
            <h3>扩展资源 · 固定版本引用</h3>
            <p className="muted">
              全局资源不会自动加载。更新版本后需保存并发布 Agent。
            </p>
            {Object.values(catalog.resources)
              .filter(
                (r: any) => (!r.owner || r.owner === v.id) && r.versions.length,
              )
              .map((r: any) => {
                const b = v.bindings.find((b: Dict) => b.id === r.id);
                return (
                  <div className="binding-row" key={r.id}>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={!!b}
                        onChange={(e) => addBinding(r, e.target.checked)}
                      />
                      <span>
                        {r.name}
                        <small>
                          {r.kind} · {r.owner ? "私有" : "全局"}
                        </small>
                      </span>
                    </label>
                    {b && (
                      <>
                        <select
                          aria-label={r.name + "版本"}
                          value={b.version}
                          onChange={(e) =>
                            update(
                              "bindings",
                              v.bindings.map((x: Dict) =>
                                x.id === r.id
                                  ? { ...x, version: Number(e.target.value) }
                                  : x,
                              ),
                            )
                          }
                        >
                          {r.versions.map((x: Dict) => (
                            <option key={x.version} value={x.version}>
                              v{x.version}
                              {x.version === r.versions.length ? " · 最新" : ""}
                            </option>
                          ))}
                        </select>
                        {b.version < r.versions.length && (
                          <span className="badge">可更新</span>
                        )}
                      </>
                    )}
                  </div>
                );
              })}
            <h3>资源执行顺序</h3>
            {v.bindings.map((b: Dict, i: number) => (
              <div className="binding-row" key={b.id}>
                <span>
                  {i + 1}. {catalog.resources[b.id]?.name || b.id}
                </span>
                <span className="grow" />
                <button
                  type="button"
                  className="icon"
                  disabled={!i}
                  onClick={() => {
                    const next = [...v.bindings];
                    [next[i - 1], next[i]] = [next[i], next[i - 1]];
                    update("bindings", next);
                  }}
                >
                  <ArrowUp size={15} />
                </button>
                <button
                  type="button"
                  className="icon"
                  disabled={i === v.bindings.length - 1}
                  onClick={() => {
                    const next = [...v.bindings];
                    [next[i + 1], next[i]] = [next[i], next[i + 1]];
                    update("bindings", next);
                  }}
                >
                  <ArrowDown size={15} />
                </button>
              </div>
            ))}
            {editor.existing && (
              <div className="actions">
                {["mcp", "skill", "hook"].map((kind) => (
                  <button
                    type="button"
                    className="secondary"
                    key={kind}
                    onClick={() => {
                      if (
                        confirm("请先保存 Agent 草稿；现在切换到私有资源编辑？")
                      )
                        onPrivate(kind, v.id);
                    }}
                  >
                    新建私有 {kind}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
        {editor.type === "resource" && (
          <>
            <Field label="归属">
              <select
                disabled={editor.existing}
                value={v.owner || ""}
                onChange={(e) => update("owner", e.target.value || null)}
              >
                <option value="">全局资源库</option>
                {Object.values(catalog.agents).map((a: any) => (
                  <option key={a.id} value={a.id}>
                    {a.draft.name} · 私有
                  </option>
                ))}
              </select>
            </Field>
            {v.kind === "mcp" && (
              <>
                <Field label="连接类型">
                  <select
                    value={v.data.type}
                    onChange={(e) =>
                      update(
                        "data",
                        e.target.value === "remote"
                          ? {
                              type: "remote",
                              url: "",
                              headers: {},
                              timeout: 10000,
                              enabled: true,
                              oauth: false,
                            }
                          : {
                              type: "local",
                              command: [""],
                              environment: {},
                              cwd: "/workspace",
                              timeout: 10000,
                              enabled: true,
                            },
                      )
                    }
                  >
                    <option value="remote">远程 MCP · HTTP</option>
                    <option value="local">沙箱内命令 · stdio</option>
                  </select>
                </Field>
                {v.data.type === "remote" ? (
                  <>
                    <Field label="服务 URL">
                      <input
                        required
                        type="url"
                        value={v.data.url}
                        onChange={(e) => data("url", e.target.value)}
                      />
                    </Field>
                    <KeyValues
                      label="请求 headers / 认证"
                      value={v.data.headers}
                      onChange={(x) => data("headers", x)}
                    />
                  </>
                ) : (
                  <>
                    <Field label="可执行文件">
                      <input
                        required
                        value={v.data.command[0] || ""}
                        onChange={(e) =>
                          data("command", [
                            e.target.value,
                            ...v.data.command.slice(1),
                          ])
                        }
                      />
                    </Field>
                    <Field label="参数（每行一个）">
                      <textarea
                        value={v.data.command.slice(1).join("\n")}
                        onChange={(e) =>
                          data("command", [
                            v.data.command[0],
                            ...e.target.value.split("\n"),
                          ])
                        }
                      />
                    </Field>
                    <Field label="沙箱工作目录">
                      <input
                        value={v.data.cwd || "/workspace"}
                        onChange={(e) => data("cwd", e.target.value)}
                      />
                    </Field>
                    <KeyValues
                      label="环境变量"
                      value={v.data.environment}
                      onChange={(x) => data("environment", x)}
                    />
                  </>
                )}
                <Field label="超时（毫秒）">
                  <input
                    type="number"
                    min="1"
                    max="120000"
                    value={v.data.timeout}
                    onChange={(e) => data("timeout", Number(e.target.value))}
                  />
                </Field>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={v.data.enabled !== false}
                    onChange={(e) => data("enabled", e.target.checked)}
                  />
                  启用连接
                </label>
                <p className="muted">
                  命令在服务器沙箱内运行，不自动安装依赖。首版不支持 OAuth。
                </p>
              </>
            )}
            {v.kind === "skill" && (
              <>
                <label className="dropzone">
                  <Upload size={28} />
                  <strong>{file?.name || "点击选择或拖入 Skill 附件"}</strong>
                  <span>SKILL.md 或 ZIP · 压缩包最多 20 MiB</span>
                  <input
                    type="file"
                    accept=".md,.zip"
                    onChange={(e) => setFile(e.target.files?.[0])}
                  />
                </label>
                {editor.existing && (
                  <div className="file-tree">
                    {Object.keys(editor.value.draft?.files || {}).map((p) => (
                      <div key={p}>{p}</div>
                    ))}
                  </div>
                )}
              </>
            )}
            {v.kind === "hook" && (
              <>
                <Field label="入口文件">
                  <select
                    value={v.data.entry}
                    onChange={(e) => {
                      const code = v.data.sources[v.data.entry] || "";
                      update("data", {
                        entry: e.target.value,
                        sources: { [e.target.value]: code },
                      });
                    }}
                  >
                    {[
                      "hook.mjs",
                      "hook.js",
                      "hook.ts",
                      ...(!["hook.mjs", "hook.js", "hook.ts"].includes(
                        v.data.entry,
                      )
                        ? [v.data.entry]
                        : []),
                    ].map((e) => (
                      <option key={e}>{e}</option>
                    ))}
                  </select>
                </Field>
                <Field label="OpenCode 插件源码">
                  <textarea
                    spellCheck={false}
                    className="code-editor hook-source"
                    value={v.data.sources?.[v.data.entry] || ""}
                    onChange={(e) =>
                      data("sources", {
                        ...v.data.sources,
                        [v.data.entry]: e.target.value,
                      })
                    }
                  />
                </Field>
                <p className="muted">
                  保存为服务器草稿。发布时静态校验和隔离加载；已绑定旧版本的
                  Agent 不受影响。
                </p>
              </>
            )}
            {editor.existing && (
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={v.archived || false}
                  onChange={(e) => update("archived", e.target.checked)}
                />
                归档资源（保留已有引用）
              </label>
            )}
          </>
        )}
        {editor.type === "model" && (
          <ProviderFields
            value={v}
            parameters={parameters}
            onTemplate={(values) => setV((old) => ({ ...old, ...values }))}
          />
        )}
        <FormConfigPreview
          type={editor.type}
          value={v}
          parameters={parameters}
        />
        <footer className="modal-footer">
          <span className="muted">保存草稿 ≠ 发布生效</span>
          <button type="button" className="secondary" onClick={close} disabled={busy}>
            取消
          </button>
          <button className="primary" disabled={busy}>
            保存到服务器
          </button>
        </footer>
      </form>
    </div>
  );
}
function Connection({
  boot,
  onSaved,
  run,
  busy,
}: {
  busy: boolean;
  boot: Dict;
  onSaved: (v: Dict) => void;
  run: (fn: () => Promise<any>, message?: string) => Promise<any>;
}) {
  const [url, setUrl] = useState(boot.url),
    [token, setToken] = useState(""),
    [remember, setRemember] = useState(false);
  const [testResult, setTestResult] = useState<Dict | null>(null);
  return (
    <div className="panel connection-form">
      <h2>服务器连接</h2>
      <p className="muted">
        配置保存在本机。管理员凭据只由本地服务用于请求服务器。
      </p>
      <Field label="API 地址">
        <input value={url} onChange={(e) => { setUrl(e.target.value); setTestResult(null); }} />
      </Field>
      <Field label="管理员凭据">
        <input
          type="password"
          autoComplete="off"
          placeholder={
            boot.credential_configured
              ? "已配置，留空保留"
              : "输入部署时生成的管理员凭据"
          }
          value={token}
          onChange={(e) => { setToken(e.target.value); setTestResult(null); }}
        />
      </Field>
      {boot.credential_persistence_available && <label className="checkbox">
        <input
          type="checkbox"
          checked={remember}
          onChange={(e) => setRemember(e.target.checked)}
        />
        保存到 Windows Credential Manager
      </label>}
      {!boot.credential_persistence_available && <p className="muted">本机仅保存服务器地址；管理员凭据保留在当前服务进程内，重启本地服务后需重新填写。</p>}
      {!url.startsWith("https:") && (
        <div className="notice warning">
          HTTP 连接未加密，凭据和模型密钥将通过明文网络传输。
        </div>
      )}
      <div className="actions">
        <button
          className="primary"
          disabled={busy}
          onClick={() =>
            run(async () => {
              await request("/local/connection", "PUT", {
                url: url.trim(),
                token: token.trim() || undefined,
                remember,
              });
              const b = await bootstrap();
              onSaved(b);
              setToken("");
              return b;
            }, "连接已保存")
          }
        >
          保存连接
        </button>
        <button
          className="secondary"
          disabled={busy}
          onClick={() =>
            run(
              async () => {
                setTestResult(null);
                await request("/local/connection", "PUT", {
                  url: url.trim(), token: token.trim() || undefined, remember,
                });
                onSaved(await bootstrap());
                setToken("");
                const result = await request("/local/connection/test", "POST", {});
                setTestResult(result);
                return result;
              },
              "管理员凭据验证通过",
            )
          }
        >
          {busy ? "正在保存并检查…" : "保存并测试连接"}
        </button>
      </div>
      {testResult && (
        <div className={"notice setup-notice " + (testResult.ready?.ok ? "success" : "warning")} role="status">
          {testResult.ready?.ok ? "凭据有效，服务器已就绪。" : <>
            <p>凭据有效，管理功能可用；部分服务尚未就绪：</p>
            <p>{Object.entries(testResult.ready?.modules || {}).filter(([, ready]) => !ready).map(([name]) => name).join("、") || "请检查服务器服务状态"}</p>
            <p>若 model_gateway 未就绪，请先导入并发布模型网关，再启用并发布 Agent。无需更换管理员凭据。</p>
            <a href="/admin">配置模型</a> · <a href="/admin?tab=agents">配置 Agent</a>
          </>}
        </div>
      )}
    </div>
  );
}
function ImportModal({
  revision,
  onClose,
  onDone,
}: {
  revision: number;
  onClose: () => void;
  onDone: () => void;
}) {
  const [path, setPath] = useState(""),
    [sources, setSources] = useState<Dict[]>([]),
    [preview, setPreview] = useState<Dict | null>(null),
    [selected, setSelected] = useState<string[]>([]),
    [replace, setReplace] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    run(async () => {
      setSources(
        (await request("/local/opencode/discover", "POST", {})).sources,
      );
    });
  }, []);
  return (
    <div className="modal-backdrop">
      <section className="modal">
        <div className="section-heading">
          <h2>从本机 OpenCode 导入模型</h2>
          <button className="icon" onClick={onClose}>
            <X />
          </button>
        </div>
        <p className="muted">
          扫描 Windows 常见配置路径，或指定 JSON/JSONC 文件与项目目录。不导入
          MCP、Skills、Hook。
        </p>
        {error && <div className="notice error">{error}</div>}
        <div className="actions">
          <input
            className="grow"
            placeholder="项目目录或配置文件的完整路径"
            value={path}
            onChange={(e) => setPath(e.target.value)}
          />
          <button
            className="secondary"
            disabled={busy}
            onClick={() =>
              run(async () =>
                setSources(
                  (
                    await request(
                      "/local/opencode/discover",
                      "POST",
                      path.toLowerCase().match(/\.jsonc?$/)
                        ? { file: path }
                        : { directory: path },
                    )
                  ).sources,
                ),
              )
            }
          >
            <Search size={16} />
            查找
          </button>
          <button
            className="secondary"
            disabled={busy}
            onClick={() =>
              run(async () =>
                setSources(
                  (await request("/local/opencode/select-file", "POST", {}))
                    .sources,
                ),
              )
            }
          >
            选择文件
          </button>
        </div>
        {sources.map((s) => (
          <button
            className="file-row"
            key={s.id}
            onClick={() =>
              run(async () => {
                const p = await request("/local/opencode/preview", "POST", {
                  source_id: s.id,
                });
                setPreview(p);
                setSelected(p.models.map((m: Dict) => m.id));
              })
            }
          >
            <Code2 size={16} />
            <span>{s.path}</span>
            <ChevronRight size={16} />
          </button>
        ))}
        {!sources.length && (
          <p className="muted">未发现配置。可在上方指定文件或项目目录。</p>
        )}
        {preview && (
          <>
            <h3>导入预览</h3>
            <p className="muted">
              来源默认模型：{preview.model || "未指定"} · 小模型：
              {preview.small_model || "未指定"}。导入后到 Agent 页显式分配。
            </p>
            {preview.errors.map((e: Dict, i: number) => (
              <div className="notice error" key={i}>
                {e.provider} {e.error}
              </div>
            ))}
            {preview.models.map((m: Dict) => (
              <label className="checkbox resource-row" key={m.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(m.id)}
                  onChange={(e) =>
                    setSelected(
                      e.target.checked
                        ? [...selected, m.id]
                        : selected.filter((id) => id !== m.id),
                    )
                  }
                />
                <span>
                  <strong>{m.name}</strong>
                  <small>
                    {m.id} · {m.provider} · API key 已配置
                  </small>
                </span>
              </label>
            ))}
            <label className="checkbox">
              <input
                type="checkbox"
                checked={replace}
                onChange={(e) => setReplace(e.target.checked)}
              />
              覆盖同名模型（不删除其他模型）
            </label>
            <button
              className="primary"
              disabled={busy || preview.errors.length > 0 || !selected.length}
              onClick={() =>
                run(async () => {
                  await request("/local/opencode/import", "POST", {
                    preview_id: preview.preview_id,
                    selected,
                    replace,
                    revision,
                  });
                  onDone();
                })
              }
            >
              确认导入 {selected.length} 个模型
            </button>
          </>
        )}
      </section>
    </div>
  );
}
