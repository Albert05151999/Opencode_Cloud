/** A trace belongs to one operation; callers explicitly share it with related requests. */
export function newTraceId(): string {
  return crypto.randomUUID().replaceAll("-", "");
}

export function traceHeaders(traceId = newTraceId()): Record<string, string> {
  if (!/^[0-9a-f]{32}$/.test(traceId) || /^0+$/.test(traceId)) {
    throw new Error("Invalid trace ID");
  }
  return {
    traceparent: `00-${traceId}-${newTraceId().slice(0, 16)}-01`,
    "X-Cloud-Request-ID": crypto.randomUUID(),
  };
}
