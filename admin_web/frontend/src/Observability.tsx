import { useEffect, useRef, useState } from "react";
import { Activity, AlertCircle, ArrowLeft, Check, ChevronRight, Clock3, Copy, Layers, RefreshCw, Search } from "lucide-react";
import { Dict, remote } from "./api";
import { durationLabel, isFailure, orderedSpans, traceExtent } from "./observability-view";
import "./observability.css";

const titles: Record<string,string> = {api_gateway:"API 网关",sandbox_manager:"沙箱管理",catalog_service:"配置目录",file_service:"文件服务",model_gateway:"模型网关",operations:"运维服务",observability:"日志服务",agent_runtime:"Agent 运行时"};
const stages: Record<string,string> = {tool_complete:"工具执行完成",tool_error:"工具执行失败",http_request:"HTTP 请求",model_dispatch:"发送模型请求",admission:"准入检查",lock_wait:"等待用户锁",admission_locked:"锁内准入",catalog:"读取 Agent 配置",workspace:"准备工作区",docker_lookup:"查找容器",docker_create:"创建容器",docker_start:"启动容器",readiness:"等待服务就绪"};
const time = (v: string) => { const d = new Date(v); return Number.isNaN(d.getTime()) ? "时间未记录" : d.toLocaleTimeString("zh-CN",{hour12:false}) + "." + String(d.getMilliseconds()).padStart(3,"0"); };
function State({row}: {row: Dict}) { return <span className={`obs-state ${isFailure(row) ? "bad" : row.status_code != null || row.status === "ok" ? "good" : "neutral"}`}>{isFailure(row) ? "异常" : row.status_code != null || row.status === "ok" ? "成功" : "事件"}{row.status_code ? ` · ${row.status_code}` : ""}</span>; }

export function Observability() {
  const initial = new URLSearchParams(location.search);
  const [view,setView]=useState("traces"), [modules,setModules]=useState<string[]>([]), [module,setModule]=useState("");
  const [session,setSession]=useState(initial.get("session")||""), [traceId,setTraceId]=useState(initial.get("trace")||""), [job,setJob]=useState("");
  const [recent,setRecent]=useState<Dict[]>([]), [logs,setLogs]=useState<Dict[]>([]), [trace,setTrace]=useState<Dict|null>(null), [selected,setSelected]=useState<Dict|null>(null);
  const [error,setError]=useState(""), [busy,setBusy]=useState(false), [partial,setPartial]=useState(false), [errorsOnly,setErrorsOnly]=useState(false), [copied,setCopied]=useState(false);
  const sequence=useRef(0), openingTrace=useRef(false);
  async function openTrace(id:string) {
    if(!/^[0-9a-f]{32}$/.test(id)) { setError("请输入 32 位十六进制 Trace ID。"); return; }
    openingTrace.current=true;
    const seq=++sequence.current; setBusy(true);setError("");setSelected(null);setModule("");setTrace(null);setTraceId(id);setView("traces");
    try { const result=await remote(`/cloud/traces/${id}`);if(seq===sequence.current)setTrace(result); }
    catch(e:any){if(seq===sequence.current)setError(e.message);}finally{if(seq===sequence.current){setBusy(false);openingTrace.current=false;}}
  }
  async function search(explicit=true) {
    if(explicit && view==="traces" && traceId.trim()) { await openTrace(traceId.trim());return; }
    const seq=++sequence.current;setBusy(true);setError("");
    try {
      const query=new URLSearchParams(view==="logs" ? {module,trace_id:traceId.trim(),job_id:job,limit:"100"} : {...(session.trim()?{session_id:session.trim()}:{}),limit:"50"});
      const result=await remote(`${view==="logs"?"/cloud/logs":"/cloud/traces"}?${query}`);
      if(seq!==sequence.current)return;
      if(view==="logs")setLogs(result.items||[]);else setRecent(result.items||[]);
      setPartial(Boolean(result.truncated||result.partial));
    }catch(e:any){if(seq===sequence.current)setError(e.message);}finally{if(seq===sequence.current)setBusy(false);}
  }
  useEffect(()=>{let active=true;remote("/cloud/logs/modules").then(r=>{if(active)setModules(r.items||[]);}).catch(()=>{});return()=>{active=false;sequence.current++;};},[]);
  useEffect(()=>{if(view==="traces"&&openingTrace.current)return;void search(false);},[view]);
  useEffect(()=>{const id=initial.get("trace");if(id)void openTrace(id);},[]);
  const spans=orderedSpans(trace?.spans||[]), extent=traceExtent(spans);
  const events: Dict[]=selected ? selected.events || (trace?.events||[]).filter((e:Dict)=>e.span_id===selected.span_id) : trace?.events||logs;
  const shown=events.filter(e=>(!errorsOnly||isFailure(e))&&(!module||e.module===module));
  const traceModules:string[]=trace?.summary?.modules || [...new Set<string>(spans.map(s=>s.module).filter(Boolean))];
  function logTable(rows:Dict[]) { return <div className="obs-table-scroll"><table className="obs-table"><thead><tr><th>时间</th><th>状态</th><th>模块 / 事件</th><th>耗时</th><th>定位信息</th></tr></thead><tbody>{rows.map((e,i)=><tr key={`${e.span_id}-${i}`} className={isFailure(e)?"obs-error-row":""}><td className="obs-mono">{time(e.timestamp)}</td><td><State row={e}/></td><td><strong>{titles[e.module]||e.module||"未知模块"}</strong><small>{stages[e.stage||e.action]||e.stage||e.action||"事件"}{e.tool ? ` · ${e.tool}` : ""}</small></td><td className="obs-mono">{durationLabel(e.duration_ms)}</td><td><span className="obs-path">{e.error_code || [e.method,e.path].filter(Boolean).join(" ") || e.session_id || "—"}</span>{e.trace_id&&<button className="obs-link obs-mono" onClick={()=>void openTrace(e.trace_id)} title={e.trace_id}>trace {e.trace_id.slice(0,12)}<ChevronRight size={12}/></button>}</td></tr>)}</tbody></table>{!rows.length&&<div className="obs-empty">当前条件下没有日志。可以取消筛选或查询其他请求。</div>}</div>; }
  return <section className="observability-workspace" aria-label="日志与调用链">
    <div className="obs-heading"><div><p className="obs-eyebrow">OBSERVABILITY</p><h2>日志与调用链</h2><p className="muted">从一次用户请求，定位到具体模块、耗时与错误。</p></div><button className="secondary" disabled={busy} onClick={()=>void (trace ? openTrace(trace.trace_id):search(false))}><RefreshCw size={15}/> 刷新</button></div>
    <div className="obs-tabs" role="tablist" aria-label="查询方式"><button role="tab" aria-selected={view==="traces"} className={view==="traces"?"active":""} onClick={()=>{openingTrace.current=false;setTrace(null);setSelected(null);setView("traces");}}><Activity size={16}/>请求调用链</button><button role="tab" aria-selected={view==="logs"} className={view==="logs"?"active":""} onClick={()=>{openingTrace.current=false;setTrace(null);setSelected(null);setView("logs");}}>模块日志</button></div>
    {!trace&&<form className="obs-filters" onSubmit={e=>{e.preventDefault();void search();}}>
      <label className="obs-wide">Trace ID<input aria-label="追踪 ID" placeholder="输入 Trace ID，查看整条请求" value={traceId} onChange={e=>setTraceId(e.target.value)}/></label>
      {view==="traces"?<label>会话 ID<input aria-label="会话 ID" placeholder="按 session_id 查找会话请求" value={session} onChange={e=>setSession(e.target.value)}/></label>:<><label>模块<select aria-label="日志模块" value={module} onChange={e=>setModule(e.target.value)}><option value="">全部模块</option>{modules.map(m=><option key={m} value={m}>{titles[m]||m}</option>)}</select></label><label>任务 ID<input aria-label="任务 ID" value={job} onChange={e=>setJob(e.target.value)} placeholder="job_id"/></label></>}
      <button className="primary" disabled={busy}><Search size={15}/>{busy?"查询中…":"查询"}</button>
    </form>}
    {error&&<div role="alert" className="notice error"><AlertCircle size={16}/>{error}</div>}
    {busy&&<p role="status" className="obs-loading">正在读取请求与日志…</p>}
    {!trace&&view==="traces"&&<section className="obs-card"><div className="obs-card-heading"><h3>最近请求</h3><span className="muted">{recent.length} 条 · 健康检查已过滤</span></div><div className="obs-table-scroll"><table className="obs-table"><thead><tr><th>时间 / Trace ID</th><th>请求</th><th>状态</th><th>模块</th><th>耗时</th><th></th></tr></thead><tbody>{recent.map(r=><tr key={r.trace_id}><td><strong>{time(r.started_at)}</strong><small className="obs-mono">{r.trace_id.slice(0,16)}…</small></td><td><span className="obs-path">{[r.method,r.path].filter(Boolean).join(" ")||"跨模块操作"}</span><small>{r.session_id||"无会话关联"}</small></td><td><State row={{...r,status:r.error?"error":undefined}}/></td><td>{(r.modules||[]).length} 个模块<small>{r.span_count} 个阶段</small></td><td className="obs-mono">{durationLabel(r.duration_ms)}</td><td><button className="secondary" onClick={()=>void openTrace(r.trace_id)}>查看调用链 <ChevronRight size={14}/></button></td></tr>)}</tbody></table>{!recent.length&&!busy&&<div className="obs-empty"><Activity size={28}/><h3>等待第一条请求</h3><p>发起会话后刷新，或粘贴 Trace ID 查看已有请求。</p></div>}</div></section>}
    {trace&&<>
      <div className="obs-trace-heading"><button className="obs-link" onClick={()=>{setTrace(null);setSelected(null);setTraceId("");void search(false);}}><ArrowLeft size={15}/>返回请求列表</button><span className="obs-mono">{trace.trace_id}</span><button aria-label="复制 Trace ID" title="复制 Trace ID" onClick={()=>{navigator.clipboard.writeText(trace.trace_id).then(()=>{setCopied(true);setTimeout(()=>setCopied(false),1500);}).catch(()=>setError("复制失败，请手动选择 Trace ID。"));}}>{copied?<Check size={16}/>:<Copy size={16}/>}</button></div>
      <div className="obs-metrics"><div><Clock3 size={18}/><span>观测时间范围</span><strong>{durationLabel(trace.summary?.duration_ms??extent)}</strong></div><div><Layers size={18}/><span>经过模块</span><strong>{traceModules.length}<small>个</small></strong></div><div><Activity size={18}/><span>执行阶段</span><strong>{spans.length}<small>个</small></strong></div><div className={spans.some(isFailure)?"has-error":""}><AlertCircle size={18}/><span>异常阶段</span><strong>{spans.filter(isFailure).length}<small>个</small></strong></div></div>
      <div className="obs-coverage"><span className={`obs-state ${trace.truncated||trace.partial?"warn":"neutral"}`}>{trace.truncated||trace.partial?"部分记录":"已扫描保留日志"}</span><span>时间范围包含并行阶段，不等于各模块耗时相加。未记录的阶段不会补成 0 ms。</span></div>
      <div className="obs-module-strip">{traceModules.map(m=><button key={m} className={module===m?"active":""} onClick={()=>setModule(module===m?"":m)}><span>{titles[m]||m}</span><strong>{durationLabel(trace.summary?.module_duration_ms?.[m])}</strong></button>)}</div>
      <section className="obs-card" aria-label="调用链详情"><div className="obs-card-heading"><div><h3>执行时间瀑布</h3><p className="muted">点击阶段查看日志；缩进表示父子调用，横条表示实际记录的时间区间。</p></div><span className="obs-mono">{durationLabel(extent)}</span></div><div className="obs-waterfall"><div className="obs-waterfall-head"><span>模块 / 阶段</span><span>相对开始时间 →</span><span>耗时</span></div>{spans.filter(s=>!module||s.module===module).map(s=><button key={s.span_id} className={`obs-span ${selected?.span_id===s.span_id?"selected":""} ${isFailure(s)?"failed":""}`} onClick={()=>setSelected(s)}><span className="obs-span-name" style={{paddingLeft:12+s.depth*16}}><strong>{titles[s.module]||s.module||"未知模块"}</strong><small>{stages[s.name]||s.name||s.span_id}{s.events?.[0]?.tool ? ` · ${s.events[0].tool}` : ""}{s.external_parent?" · 外部父跨度":""}</small></span><span className="obs-track">{typeof s.duration_ms==="number"&&typeof s.offset_ms==="number"&&extent!=null?<span className="obs-bar" style={{left:`${Math.min(99,s.offset_ms/Math.max(extent,1)*100)}%`,width:`${Math.max(.5,Math.min(100,s.duration_ms/Math.max(extent,1)*100))}%`}}/>:<span className="obs-unknown">瞬时事件 / 未记录耗时</span>}</span><span className="obs-mono">{durationLabel(s.duration_ms)}{isFailure(s)&&<AlertCircle size={13}/>}</span></button>)}</div>{!spans.length&&<div className="obs-empty">未检索到跨度。记录可能不在当前保留或扫描范围内。</div>}</section>
    </>}
    {(trace||view==="logs")&&<section className="obs-card"><div className="obs-card-heading"><div><h3>{selected?`${titles[selected.module]||selected.module} · 阶段日志`:"关联日志"}</h3><p className="muted">{shown.length} 条事件{selected?` · span ${selected.span_id}`:""}</p></div><div className="actions">{selected&&<button className="secondary" onClick={()=>setSelected(null)}>全部阶段</button>}<label className="checkbox"><input type="checkbox" checked={errorsOnly} onChange={e=>setErrorsOnly(e.target.checked)}/>仅异常</label></div></div>{logTable(shown)}{selected&&<details className="obs-raw"><summary>查看结构化阶段数据</summary><pre>{JSON.stringify(selected,null,2)}</pre></details>}</section>}
    {(partial||trace?.truncated)&&<p className="obs-footnote">记录受保留期、扫描上限或结果数量限制；没有显示的记录不能视为没有发生。可按 Trace ID 缩小检索范围。</p>}
  </section>;
}
