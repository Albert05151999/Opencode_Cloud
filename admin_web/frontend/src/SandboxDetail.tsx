import { operationLabel } from "./operation-labels";
import { useEffect, useState } from "react";
import { Dict, remote } from "./api";

export function SandboxDetail({
  id,
  onClose,
  onJob,
}: {
  id: string;
  onClose: () => void;
  onJob: (id: string) => void;
}) {
  const [data, setData] = useState<Dict | null>(null),
    [impact, setImpact] = useState<Dict | null>(null),
    [confirmation, setConfirmation] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function refresh() {
    try {
      setData(await remote(`/cloud/admin/sandboxes/${encodeURIComponent(id)}`));
      setError("");
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => {
    void refresh();
  }, [id]);
  async function force(action: string) {
    if (!impact) return;
    setBusy(true);
    try {
      const job = await remote(
        `/cloud/admin/sandboxes/${encodeURIComponent(id)}/${action}`,
        "POST",
        {
          request_id: crypto.randomUUID(),
          force_preview_id: impact.preview_id,
          confirmation,
        },
      );
      onJob(job.job_id);
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel" role="dialog" aria-label="沙箱详情">
      <div className="actions">
        <h3>{id}</h3>
        <button onClick={refresh}>刷新详情</button>
        <button onClick={onClose}>关闭详情</button>
      </div>
      {error && <p role="alert">{error}</p>}
      {data && (
        <>
          <p>
            容器：{operationLabel(data.container_state)} · 健康：{operationLabel(data.status)} · 任务：
            {operationLabel(data.execution)} · 配置版本：{data.configuration_version ?? "未知"}
          </p>
          <p>
            CPU：{data.cpu_percent == null ? "未知" : `${data.cpu_percent}%`} ·
            内存：
            {data.memory_bytes == null
              ? "未知"
              : `${(data.memory_bytes / 1024 / 1024).toFixed(1)} MiB`}{" "}
            · 采样：{data.sampled_at ? new Date(data.sampled_at * 1000).toLocaleTimeString() : "未知"}
          </p>
          <h4>受此沙箱影响的会话</h4>
          {(Array.isArray(data.sessions) ? data.sessions : []).map((s: Dict) => (
            <p key={s.session_id}>
              {s.session_id} · {s.execution?.type || "未知"}
            </p>
          ))}
          <h4>最近操作</h4>
          {(data.operations || []).map((j: Dict) => (
            <p key={j.id}>
              {operationLabel(j.kind)} · {operationLabel(j.status)}
              {j.interrupted_sessions?.length ? " · 已记录会话中断" : ""}
            </p>
          ))}
          <button
            disabled={busy}
            onClick={async () => {
              try {
                setImpact(
                  await remote(
                    `/cloud/admin/sandboxes/${encodeURIComponent(id)}/force-preview`,
                  ),
                );
                setConfirmation("");
              } catch (e: any) {
                setError(e.message);
              }
            }}
          >
            查看强制操作影响
          </button>
        </>
      )}
      {impact && (
        <div className="notice warning">
          <p>
            强制操作会中断此沙箱中的任务，不会自动重发请求。受影响会话：
            {(impact.sessions || []).map((s: any) => typeof s === "string" ? s : s.session_id).join("、") || "暂无已登记会话"}；任务状态：
            {impact.execution}。
          </p>
          <label>
            输入完整沙箱 ID 确认
            <input
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
            />
          </label>
          <button
            disabled={busy || confirmation !== id}
            onClick={() => force("stop")}
          >
            强制停止
          </button>
          <button
            disabled={busy || confirmation !== id}
            onClick={() => force("restart")}
          >
            强制重启
          </button>
        </div>
      )}
    </section>
  );
}
