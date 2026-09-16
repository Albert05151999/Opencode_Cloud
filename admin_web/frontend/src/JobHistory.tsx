import { navigateTo } from "./navigation";
import { useEffect, useRef, useState } from "react";
import { Dict, remote } from "./api";
import { operationLabel, localTime } from "./operation-labels";

export function JobHistory() {
  const [offset, setOffset] = useState(0), [data, setData] = useState<Dict>({ items: [], total: 0 });
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [detail, setDetail] = useState<Dict | null>(null);
  const generation = useRef(0);
  const pending = useRef(false);
  const detailPanel = useRef<HTMLElement>(null);
  useEffect(() => { if (detail) { detailPanel.current?.scrollIntoView({block:"nearest"}); detailPanel.current?.focus(); } }, [detail?.id]);
  async function refresh() {
    const id = ++generation.current;
    pending.current = true;
    setBusy(true);
    try { const value = await remote(`/cloud/admin/jobs?offset=${offset}&limit=25`); if (id === generation.current) { setData(value); setError(''); } }
    catch (e: any) { if (id === generation.current) setError(e.message); }
    finally { if (id === generation.current) { pending.current = false; setBusy(false); } }
  }
  useEffect(() => {
    void refresh();
    const t = setInterval(() => { if (!document.hidden && !pending.current) void refresh(); }, 5000);
    return () => { ++generation.current; pending.current = false; clearInterval(t); };
  }, [offset]);
  const shown = detail && (data.items.find((j: Dict) => j.id === detail.id) || detail);
  return <section className="panel">
    <div className="section-heading"><h3>任务记录</h3><button className="secondary" disabled={busy} onClick={refresh}>{busy ? '加载中…' : '刷新任务'}</button></div>
    <p className="muted">每 5 秒更新。查看任务详情可核对执行阶段、错误和关联调用链。</p>
    {error && <p className="notice error" role="alert">{error}</p>}
    {!busy && !data.items.length && <p className="muted">暂无发布或运维任务。提交操作后可在这里跟踪结果。</p>}
    {data.items.map((j: Dict) => <div className="resource-row" key={j.id}>
      <div className="grow"><strong>{operationLabel(j.kind)} · {j.target === '*' ? '全局' : j.target}</strong>
        <p>{localTime(j.created)} · <span className="badge">{operationLabel(j.status)}</span></p>
        {j.error && <p className="notice error">{j.error}</p>}
        {['needs_recovery','interrupted'].includes(j.status) && <p className="notice">结果待核对，请先检查详情中的执行阶段再操作。</p>}
      </div>
      <button className="secondary" onClick={async () => { try { setDetail(await remote(`/cloud/admin/jobs/${encodeURIComponent(j.id)}`)); } catch(e: any) { setError(e.message); } }}>查看详情</button>
      {['queued','validating','waiting'].includes(j.status) && j.kind !== 'agent.delete' && <button className="secondary" disabled={busy} onClick={async () => {
        if (!confirm(`取消“${operationLabel(j.kind)} · ${j.target}”？`)) return;
        setBusy(true);
        try { await remote(`/cloud/admin/jobs/${encodeURIComponent(j.id)}/cancel`, 'POST', {}); await refresh(); }
        catch(e: any) { setError(e.message); } finally { setBusy(false); }
      }}>取消任务</button>}
    </div>)}
    {shown && <section ref={detailPanel} tabIndex={-1} className="panel" role="region" aria-label="任务详情">
      <div className="section-heading"><h3>任务详情</h3><button className="secondary" onClick={() => setDetail(null)}>关闭详情</button></div>
      <p>{operationLabel(shown.kind)} · {shown.target} · {operationLabel(shown.status)}</p>
      <p>创建：{localTime(shown.created)} · 更新：{localTime(shown.updated)}</p>
      <p>执行阶段：{operationLabel(shown.checkpoint)}</p><p>任务 ID：<code>{shown.id}</code></p>
      {shown.trace_id && <p>Trace ID：<code>{shown.trace_id}</code> <button className="secondary" onClick={() => navigateTo(`/admin?tab=logs&trace=${encodeURIComponent(shown.trace_id)}`)}>查看调用链</button></p>}
      {shown.error && <p role="alert" className="notice error">{shown.error}</p>}
    </section>}
    <div className="actions"><button className="secondary" disabled={busy || !offset} onClick={() => setOffset(Math.max(0, offset - 25))}>上一页</button>
      <span>{data.total ? offset + 1 : 0}–{Math.min(offset + 25, data.total)} / {data.total} 条</span>
      <button className="secondary" disabled={busy || offset + 25 >= data.total} onClick={() => setOffset(offset + 25)}>下一页</button></div>
  </section>;
}
