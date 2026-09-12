import {useEffect, useRef, useState} from 'react';
import {RefreshCw, Download, Play, Square, Trash2} from 'lucide-react';
import {Dict, download, remote} from './api';

const active = new Set(['queued', 'preparing', 'running', 'cancelling']);
const names: Record<string, string> = {
  queued: '排队中', preparing: '准备沙箱', ready: '会话已准备', running: '压测中',
  cancelling: '正在停止', cancelled: '已取消', interrupted: '已中断', completed: '已完成',
  completed_with_errors: '完成（有失败）', failed: '失败', succeeded: '成功',
  prepare_failed: '准备失败', timed_out: '请求超时', retained: '数据已保留', cleaning: '清理中', cleaned: '已清理',
};
const label = (value: string) => names[value] || value;
const number = (value: number | null | undefined, suffix = '') => value == null ? '—' : `${value.toLocaleString(undefined, {maximumFractionDigits: 2})}${suffix}`;

export function LoadTests() {
  const [options, setOptions] = useState<Dict | null>(null);
  const [capacity, setCapacity] = useState<Dict | null>(null);
  const [now, setNow] = useState(Date.now());
  const [choices, setChoices] = useState<Record<string, Dict>>({});
  const [timeout, setTimeoutValue] = useState(180);
  const [runs, setRuns] = useState<Dict>({items: [], total: 0});
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState('');
  const [report, setReport] = useState<Dict | null>(null);
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const attempt = useRef<{key: string, id: string} | null>(null);
  const currentSelection = useRef(selected);
  currentSelection.current = selected;

  async function refresh() {
    try {
      const data = await remote(`/cloud/admin/load-tests?offset=${offset}&limit=10`);
      setRuns(data);
      setCapacity(await remote('/cloud/admin/load-tests/capacity'));
      if (selected) {
        const detail = await remote(`/cloud/admin/load-tests/${selected}`);
        if (currentSelection.current === selected) setReport(detail);
      }
      setError('');
    } catch (e: any) { setError(e.message); }
  }
  useEffect(() => {
    let disposed = false;
    remote('/cloud/admin/load-tests/options').then(data => { if (!disposed) setOptions(data); })
      .catch(e => { if (!disposed) setError(e.message); });
    return () => { disposed = true; };
  }, []);
  useEffect(() => {
    let disposed = false, pending = false, lastPoll = 0;
    async function sample() {
      if (pending || document.hidden) return;
      pending = true; lastPoll = Date.now();
      try {
        const data = await remote('/cloud/admin/load-tests/capacity');
        if (!disposed) setCapacity(data);
      } catch {
        if (!disposed) setCapacity({known: false, reasons: ['资源监测连接失败，请刷新后重试']});
      } finally { pending = false; }
    }
    void sample();
    const timer = window.setInterval(() => {
      setNow(Date.now());
      if (Date.now() - lastPoll >= 5000) void sample();
    }, 1000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, []);
  useEffect(() => {
    let disposed = false;
    async function poll() {
      try {
        const [list, detail] = await Promise.all([
          remote(`/cloud/admin/load-tests?offset=${offset}&limit=10`),
          selected ? remote(`/cloud/admin/load-tests/${selected}`) : Promise.resolve(null),
        ]);
        if (!disposed) { setRuns(list); setReport(detail); }
      } catch (e: any) { if (!disposed) setError(e.message); }
    }
    void poll();
    const timer = window.setInterval(() => { if (!document.hidden) void poll(); }, 2000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [selected, offset]);

  const agents = (options?.agents || []).filter((a: Dict) => choices[a.id]?.selected)
    .map((a: Dict) => ({agent_id: a.id, users: Number(choices[a.id].users),
      cpu_limit: Number(choices[a.id].cpu_limit), memory_mb: Number(choices[a.id].memory_mb)}));
  const count = agents.reduce((n: number, a: Dict) => n + a.users, 0);
  const cpu = agents.reduce((n: number, a: Dict) => n + a.users * a.cpu_limit, 0);
  const memory = agents.reduce((n: number, a: Dict) => n + a.users * a.memory_mb, 0);
  const inProgress = !!runs.active_id || runs.items.some((r: Dict) => active.has(r.status));
  const freshCapacity = !!capacity?.known && now - capacity.sampled_at * 1000 <= 15000;
  const fits = freshCapacity && capacity?.admission_allowed && cpu <= capacity.remaining_cpu + 1e-8 && memory <= capacity.remaining_memory_mb;
  const valid = count > 0 && count <= (options?.max_users || 100) && agents.every((a: Dict) =>
    Number.isInteger(a.users) && a.users >= 1 && a.cpu_limit >= .25 && a.cpu_limit <= 64 &&
    Number.isInteger(a.memory_mb) && a.memory_mb >= 256 && a.memory_mb <= 65536);
  function change(id: string, patch: Dict) {
    setChoices(previous => ({...previous, [id]: {users: 1, cpu_limit: 1, memory_mb: 1024, ...previous[id], ...patch}}));
  }
  async function act(fn: () => Promise<void>) {
    setBusy(true); setError('');
    try { await fn(); } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }
  async function start() {
    const body = {agents, timeout_seconds: timeout};
    const key = JSON.stringify(body);
    if (attempt.current?.key !== key) attempt.current = {key, id: crypto.randomUUID()};
    const result = await remote('/cloud/admin/load-tests', 'POST', {...body, request_id: attempt.current!.id});
    attempt.current = null;
    setReport(null); setSelected(result.id); setConfirmation(''); setOffset(0);
    setRuns(await remote('/cloud/admin/load-tests?offset=0&limit=10'));
  }

  return <div className="load-tests">
    <section className="panel">
      <div className="section-heading"><h2>自动压测</h2><button onClick={refresh}><RefreshCw size={16}/>刷新压测</button></div>
      <p>选择已发布的 Agent，创建独立模拟用户。准备完会话后，所有就绪用户同时发送一次固定请求。</p>
      {error && <p role="alert" className="notice">{error}</p>}
      <section aria-label="服务器资源状态" className="panel">
        <h3>服务器资源状态</h3>
        {!freshCapacity ? <p role="alert">资源状态未知或已过期，暂不能开始压测。</p> : <>
          <p>CPU 使用率 {number(capacity!.cpu_usage_percent, '%')} · 实际可用内存 {number(capacity!.memory_available_mb, ' MiB')} · 运行中沙箱 {capacity!.running_sandboxes}</p>
          <p>已有配额 {number(capacity!.allocated_cpu, ' 核')} / {number(capacity!.allocated_memory_mb, ' MiB')}；系统预留 {number(capacity!.reserved_cpu, ' 核')} / {number(capacity!.reserved_memory_mb, ' MiB')}。</p>
          <p><strong>还能分配 {number(capacity!.remaining_cpu, ' 核')} / {number(capacity!.remaining_memory_mb, ' MiB')}</strong></p>
          <small>采样时间 {new Date(capacity!.sampled_at * 1000).toLocaleTimeString()}，每 5 秒更新。配额计算包含可重启的已停止沙箱。</small>
        </>}
        {capacity?.reasons?.map((reason: string) => <p key={reason}>{reason}</p>)}
        {freshCapacity && count > 0 && !fits && <p role="alert">当前选择超过资源预算，或服务器负载过高；请减少用户数、降低每沙箱配额或释放资源。</p>}
        {freshCapacity && agents.map((a: Dict) => {
          const max = Math.max(0, Math.min(100, Math.floor((capacity!.remaining_cpu - (cpu - a.users * a.cpu_limit)) / a.cpu_limit), Math.floor((capacity!.remaining_memory_mb - (memory - a.users * a.memory_mb)) / a.memory_mb)));
          return <p key={a.agent_id}>{a.agent_id} 在其他行不变时最多 {Number.isFinite(max) ? max : 0} 个用户。</p>;
        })}
      </section>
      {options && !options.agents.length && <p className="notice">没有可压测的 Agent。请先创建、启用并发布 Agent。</p>}
      <div style={{overflowX: 'auto'}}><table style={{width: '100%', textAlign: 'left'}}>
        <thead><tr><th>Agent / 默认模型</th><th>模拟用户数</th><th>每沙箱 CPU（核）</th><th>每沙箱内存（MiB）</th></tr></thead>
        <tbody>{options?.agents.map((a: Dict) => <tr key={a.id}>
          <td><label><input type="checkbox" aria-label={`选择 ${a.id}`} checked={!!choices[a.id]?.selected}
            onChange={e => change(a.id, {selected: e.target.checked})}/>{a.name} · {a.id}</label><p className="muted">v{a.version} · {a.model_id}</p></td>
          <td><input type="number" min={1} max={100} aria-label={`${a.id} 用户数`} value={choices[a.id]?.users ?? 1} onChange={e => change(a.id, {users: e.target.value})}/></td>
          <td><input type="number" min={.25} max={64} step={.25} aria-label={`${a.id} CPU`} value={choices[a.id]?.cpu_limit ?? 1} onChange={e => change(a.id, {cpu_limit: e.target.value})}/></td>
          <td><input type="number" min={256} max={65536} step={256} aria-label={`${a.id} 内存`} value={choices[a.id]?.memory_mb ?? 1024} onChange={e => change(a.id, {memory_mb: e.target.value})}/></td>
        </tr>)}</tbody></table></div>
      <p role="status">计划 {count} 个用户 / {count} 个沙箱；配额合计 {number(cpu)} 核、{number(memory)} MiB。</p>
      <p className="muted">主机：{number(options?.host_capacity?.cpu_count)} 核、{number(options?.host_capacity?.memory_mb)} MiB。配额是上限，不代表独占或当前空闲资源；压测会调用真实模型并消耗额度。</p>
      <label>每用户请求超时（秒）<input aria-label="每用户请求超时（秒）" type="number" min={10} max={1800} value={timeout} onChange={e => setTimeoutValue(Number(e.target.value))}/></label>
      <details><summary>固定请求及测试范围</summary><p>{options?.prompt}</p><p>仅测试服务端的控制器、沙箱和模型链路，不包含浏览器或公网入口。沙箱准备耗时单独统计；延迟统计为成功请求的完整响应耗时。配置发布排队等待；请先停止压测，再对参与测试的 Agent 做归档或沙箱启停操作。</p></details>
      <button className="primary" disabled={busy || inProgress || !valid || !fits || timeout < 10 || timeout > 1800}
        onClick={() => void act(start)}><Play size={16}/>{inProgress ? '已有压测进行中' : '开始压测'}</button>
    </section>

    <section className="panel"><h3>压测历史</h3>
      {!runs.items.length && <p>尚无压测记录。</p>}
      {runs.items.map((r: Dict) => <button key={r.id} className="file-row" onClick={() => {setReport(null); setSelected(r.id); setConfirmation('');}}>
        <span>{r.id}<small> · {new Date(r.created_at * 1000).toLocaleString()}</small></span><span>{label(r.status)} · {label(r.cleanup_status)}</span>
      </button>)}
      <div className="actions"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 10))}>上一页</button>
        <span>{runs.total} 项</span><button disabled={offset + 10 >= runs.total} onClick={() => setOffset(offset + 10)}>下一页</button></div>
    </section>

    {report && <section className="panel" aria-label="压测报告">
      <div className="section-heading"><h3>压测报告 · {label(report.status)}</h3><div className="actions">
        <button onClick={() => void act(() => download(`/cloud/admin/load-tests/${report.id}/report?format=json`, `${report.id}.json`))}><Download size={16}/>JSON 报告</button>
        <button onClick={() => void act(() => download(`/cloud/admin/load-tests/${report.id}/report?format=csv`, `${report.id}.csv`))}>CSV 明细</button>
        {active.has(report.status) && <button disabled={busy || report.status === 'cancelling'} onClick={() => void act(async () => {await remote(`/cloud/admin/load-tests/${report.id}/cancel`, 'POST', {}); await refresh();})}><Square size={16}/>停止压测</button>}
      </div></div><p>{report.id}</p>
      <p>已准备 {report.summary.prepared}/{report.summary.users}，已提交 {report.summary.submitted}，成功 {report.summary.succeeded}，失败 {report.summary.failed}，取消 {report.summary.cancelled}。</p>
      <p>成功率 {number(report.summary.success_rate * 100, '%')} · P50 {number(report.summary.p50_ms, ' ms')} · P95 {number(report.summary.p95_ms, ' ms')} · P99 {number(report.summary.p99_ms, ' ms')}</p>
      <p>成功吞吐 {number(report.summary.successful_requests_per_second, ' 次/秒')} · 发起时间差 {number(report.summary.launch_spread_ms, ' ms')} · 输入/输出 Token {number(report.summary.input_tokens)} / {number(report.summary.output_tokens)}</p>
      {report.error && <p role="alert">{report.error}</p>}
      {Object.entries(report.by_agent).map(([aid, row]: [string, any]) => <p key={aid}>{aid}：{row.succeeded}/{row.users} 成功 · P95 {number(row.p95_ms, ' ms')} · v{report.snapshots?.[aid]?.version ?? '—'} · {report.snapshots?.[aid]?.model_id || '—'}</p>)}
      <div style={{overflowX: 'auto'}}><table style={{width: '100%', textAlign: 'left'}}>
        <thead><tr><th>Agent / 用户</th><th>沙箱 / 会话</th><th>资源配额</th><th>状态</th><th>准备 / 请求耗时</th><th>错误</th></tr></thead>
        <tbody>{report.users.map((u: Dict) => <tr key={u.username}>
          <td>{u.agent_id}<br/><small>{u.username}</small></td><td><small>{u.sandbox_id || '—'}<br/>{u.session_id || '—'}</small></td>
          <td>{number(u.cpu_limit, ' 核')}<br/>{number(u.memory_mb, ' MiB')}</td><td>{label(u.phase)}<br/>{label(u.storage_state)}</td><td>{number(u.prepare_ms, ' ms')} / {number(u.latency_ms, ' ms')}</td><td>{u.error || '—'}{u.abort_confirmed === false && <p>未确认任务终止，请清理测试沙箱</p>}</td>
        </tr>)}</tbody></table></div>
      {!active.has(report.status) && <div className="panel">
        <h4>销毁本次测试数据</h4><p>只删除本次测试用户的沙箱、会话、工作区和运行状态。会终止这些沙箱中遗留的任务；Agent、正常用户和这份报告保留。</p>
        <p>数据状态：{label(report.cleanup_status)}{report.cleanup_error && ` · ${report.cleanup_error}`}</p>
        {report.cleanup_status !== 'cleaned' && <><label>输入完整测试 ID 确认<input aria-label="输入完整测试 ID 确认" value={confirmation} onChange={e => setConfirmation(e.target.value)}/></label>
          <button disabled={busy || report.cleanup_status === 'cleaning' || confirmation !== report.id}
            onClick={() => void act(async () => {await remote(`/cloud/admin/load-tests/${report.id}/cleanup`, 'POST', {confirmation}); await refresh();})}><Trash2 size={16}/>销毁测试沙箱和用户数据</button></>}
      </div>}
    </section>}
  </div>;
}
