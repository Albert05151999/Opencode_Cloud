import { SandboxDetail } from "./SandboxDetail";
import { RecoverySettings } from "./RecoverySettings";
import { useEffect, useState } from "react";
import { RefreshCw, Search } from "lucide-react";
import { remote, Dict } from "./api";

export function Operations() {
  const [detail, setDetail] = useState<string | null>(null);
  const [query, setQuery] = useState(""),
    [filter, setFilter] = useState(""),
    [offset, setOffset] = useState(0);
  const [data, setData] = useState<Dict>({ items: [], total: 0 }),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [job, setJob] = useState<Dict | null>(null);
  async function reload() {
    try {
      setData(
        await remote(
          `/cloud/admin/sandboxes?q=${encodeURIComponent(query)}&status=${encodeURIComponent(filter)}&offset=${offset}&limit=25`,
        ),
      );
      setError("");
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      try {
        const result = await remote(
          `/cloud/admin/sandboxes?q=${encodeURIComponent(query)}&status=${encodeURIComponent(filter)}&offset=${offset}&limit=25`,
        );
        if (!disposed) {
          setData(result);
          setError("");
        }
      } catch (e: any) {
        if (!disposed) setError(e.message);
      }
    };
    void refresh();
    const timer = setInterval(() => {
      if (!document.hidden) void refresh();
    }, 5000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [query, filter, offset]);
  useEffect(() => {
    if (!job?.id) return;
    let disposed = false;
    const timer = setInterval(async () => {
      try {
        const result = await remote(`/cloud/admin/jobs/${job.id}`);
        if (disposed) return;
        setJob(result);
        if (["succeeded", "failed", "cancelled", "needs_recovery", "interrupted"].includes(result.status)) {
          clearInterval(timer);
          setBusy(false);
          if (["needs_recovery", "interrupted"].includes(result.status)) setError("操作结果需要核对，请在发布记录检查检查点与恢复状态后继续。");
          void reload();
        }
      } catch (e: any) {
        if (!disposed) {
          setError(e.message);
          setBusy(false);
          clearInterval(timer);
        }
      }
    }, 1500);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [job?.id]);
  async function operate(row: Dict, action: string) {
    if (
      !confirm(
        `${action === "stop" ? "停止" : action === "start" ? "启动" : "重启"}沙箱 ${row.sandbox_id}？将等待该 Agent 的活动任务结束，最多 120 秒；不会自动重发聊天请求。`,
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      const result = await remote(
        `/cloud/admin/sandboxes/${encodeURIComponent(row.sandbox_id)}/${action}`,
        "POST",
        { request_id: crypto.randomUUID() },
      );
      setJob({ id: result.job_id, status: "queued" });
    } catch (e: any) {
      setBusy(false);
      setError(e.message);
    }
  }
  return (
    <div className="panel">
      <RecoverySettings />
      {detail && (
        <SandboxDetail
          id={detail}
          onClose={() => setDetail(null)}
          onJob={(id) => {
            setBusy(true);
            setJob({ id, status: "queued" });
          }}
        />
      )}
      <div className="section-heading">
        <div>
          <h2>沙箱运维 · {data.total}</h2>
          <p className="muted">
            一个沙箱可承载多个会话。状态来自后台健康检查，每 5
            秒刷新；操作记录也可在发布记录查看。
          </p>
        </div>
        <button className="secondary" onClick={reload}>
          <RefreshCw size={16} />
          刷新
        </button>
      </div>
      <div className="actions">
        <Search size={16} />
        <input
          aria-label="搜索沙箱"
          placeholder="沙箱 ID / 容器 ID / Agent / 用户"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOffset(0);
          }}
        />
        <select
          aria-label="沙箱状态"
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">全部状态</option>
          {["ready", "unhealthy", "stopped", "creating", "missing"].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </div>
      {error && (
        <p role="alert" className="notice error">
          {error}
        </p>
      )}
      {job && (
        <p role="status">
          操作 {job.id} · {job.status}
          {job.error && ` · ${job.error}`}
        </p>
      )}
      {data.items.map((row: Dict) => (
        <div className="resource-row" key={row.sandbox_id}>
          <div className="grow">
            <strong>{row.sandbox_id}</strong>
            <p>
              {row.agent_id} · {row.username}
            </p>
            <p className="muted">
              容器：{row.container_id || "未创建或已回收"}
            </p>
            <p className="muted">最近活动：{row.last_active_at}</p>
            {row.recovery?.reason && (
              <p className="notice">{row.recovery.reason}</p>
            )}
          </div>
          <span className="badge">
            {row.status}
            {row.desired_state === "stopped" ? " · 人工停止" : ""}
          </span>
          <div className="actions">
            <button
              className="secondary"
              onClick={() => setDetail(row.sandbox_id)}
            >
              详情
            </button>
            {["start", "stop", "restart"].map((action) => (
              <button
                key={action}
                disabled={busy}
                className="secondary"
                onClick={() => operate(row, action)}
              >
                {action === "start"
                  ? "启动"
                  : action === "stop"
                    ? "停止"
                    : "重启"}
              </button>
            ))}
          </div>
        </div>
      ))}
      {!data.items.length && (
        <p className="muted">没有匹配的沙箱；首次聊天时按需创建。</p>
      )}
      <div className="actions">
        <button
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 25))}
        >
          上一页
        </button>
        <span>
          {offset + 1}–{Math.min(offset + 25, data.total)} / {data.total}
        </span>
        <button
          disabled={offset + 25 >= data.total}
          onClick={() => setOffset(offset + 25)}
        >
          下一页
        </button>
      </div>
    </div>
  );
}
