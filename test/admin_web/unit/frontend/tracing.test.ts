import { test } from "node:test";
import assert from "node:assert/strict";
import { newTraceId, traceHeaders } from "../../../../admin_web/frontend/src/tracing.ts";

test("related operations retain trace but use independent request and span IDs", () => {
  const trace = newTraceId();
  const a = traceHeaders(trace), b = traceHeaders(trace);
  assert.equal(a.traceparent.split("-")[1], trace);
  assert.equal(b.traceparent.split("-")[1], trace);
  assert.notEqual(a.traceparent, b.traceparent);
  assert.notEqual(a["X-Cloud-Request-ID"], b["X-Cloud-Request-ID"]);
  assert.notEqual(traceHeaders().traceparent.split("-")[1], trace);
});

test("invalid or zero trace identifiers cannot be propagated", () => {
  for (const value of ["", "0".repeat(32), "g".repeat(32), "a".repeat(31)]) {
    assert.throws(() => traceHeaders(value));
  }
});
