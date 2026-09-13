export type EventRow = Record<string, any>;

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
