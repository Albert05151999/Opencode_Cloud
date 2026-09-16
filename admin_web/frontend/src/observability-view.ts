export type EventRow = Record<string, any>;

export function spanOperation(span: EventRow, spans: EventRow[]): string {
  const events: EventRow[] = span.events || [];
  const http = events.find(e => e.path) || {};
  const path = http.path || "";
  if (span.module === "model_gateway" && span.name === "http_request") {
    const calls = orderedSpans(spans).filter(s => s.module === "model_gateway" && s.name === "http_request");
    const model = events.find(e => e.logical_model)?.logical_model;
    return `模型调用 #${calls.findIndex(s => s.span_id === span.span_id) + 1}${model ? ` · ${model}` : ""}（含上游）`;
  }
  if (span.name !== "http_request") return "";
  const action = path === "/session" && http.method === "POST" ? "创建会话"
    : /\/session\/[^/]+\/prompt_async$/.test(path) ? "提交消息（异步接收）"
    : /\/session\/[^/]+\/message$/.test(path) && http.method === "POST" ? "发送消息并等待回复"
    : /\/agents\/[^/]+\/authorize$/.test(path) ? "检查 Agent 调用权限"
    : /\/agents\/[^/]+\/bundle$/.test(path) ? "读取已发布 Agent 配置"
    : path.endsWith("/workspaces/allocate") ? "分配或复用会话工作目录"
    : path.endsWith("/file-admission") ? "检查文件服务准入"
    : path.endsWith("/admission") ? "检查平台准入"
    : [http.method, path].filter(Boolean).join(" ") || "处理 HTTP 请求";
  return span.module === "sandbox_manager" ? `路由至沙箱 · ${action}` : action;
}

export function spanContext(span: EventRow): string {
  const events: EventRow[] = span.events || [];
  const http = events.find(e => e.path);
  const tool = events.find(e => e.tool)?.tool;
  return [span.module || "未知 module", http && [http.method, http.path].filter(Boolean).join(" "), tool].filter(Boolean).join(" · ");
}

export function durationLabel(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "未记录";
  if (value >= 1000) return `${(value / 1000).toFixed(2)} s`;
  return `${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })} ms`;
}

export function isFailure(row: EventRow): boolean {
  return Boolean(row.error_code) || Number(row.status_code) >= 400 ||
    ["ERROR", "CRITICAL"].includes(row.level) || row.status === "error";
}

export function orderedSpans(spans: EventRow[]): (EventRow & { depth: number })[] {
  spans = [...spans].sort((a, b) => (a.offset_ms ?? Number.MAX_SAFE_INTEGER) - (b.offset_ms ?? Number.MAX_SAFE_INTEGER));
  const byId = new Map(spans.map(span => [span.span_id, span]));
  const result: (EventRow & { depth: number })[] = [];
  const visited = new Set<string>();
  const children = new Map<string, EventRow[]>();
  for (const span of spans) {
    if (span.parent_span_id && byId.has(span.parent_span_id)) {
      const list = children.get(span.parent_span_id) || [];
      list.push(span); children.set(span.parent_span_id, list);
    }
  }
  function visit(span: EventRow, depth: number) {
    if (visited.has(span.span_id)) return;
    visited.add(span.span_id); result.push({ ...span, depth });
    for (const child of children.get(span.span_id) || []) visit(child, Math.min(depth + 1, 8));
  }
  for (const span of spans) if (!byId.has(span.parent_span_id)) visit(span, 0);
  // Corrupt/cyclic parent references remain inspectable, without recursive loops.
  for (const span of spans) visit(span, 0);
  return result;
}

export function traceExtent(spans: EventRow[]): number | null {
  const ends = spans.filter(s => typeof s.offset_ms === "number" &&
    typeof s.duration_ms === "number" && Number.isFinite(s.offset_ms) && Number.isFinite(s.duration_ms))
    .map(s => Math.max(0, s.offset_ms) + Math.max(0, s.duration_ms));
  return ends.length ? Math.max(...ends) : null;
}

export function visibleSpans(spans: EventRow[], expanded: Set<string>): EventRow[] {
  const ordered = orderedSpans(spans), visible: EventRow[] = [];
  let collapsedDepth: number | null = null;
  for (const span of ordered) {
    if (collapsedDepth !== null && span.depth > collapsedDepth) continue;
    collapsedDepth = null;
    visible.push(span);
    if (!expanded.has(span.span_id)) collapsedDepth = span.depth;
  }
  return visible;
}
