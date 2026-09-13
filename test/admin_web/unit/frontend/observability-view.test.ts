import { test } from "node:test";
import assert from "node:assert/strict";
import { durationLabel, isFailure, orderedSpans, traceExtent } from "../../../../admin_web/frontend/src/observability-view.ts";

test("missing timing stays unknown and overlapping spans are not added", () => {
  assert.equal(durationLabel(null), "未记录");
  assert.equal(durationLabel(0), "0 ms");
  assert.equal(durationLabel(NaN), "未记录");
  assert.equal(traceExtent([{ offset_ms: 0, duration_ms: 100 }, { offset_ms: 25, duration_ms: 50 }]), 100);
  assert.equal(traceExtent([{ duration_ms: null }]), null);
});
test("HTTP and recorded errors remain visible even when logger level is INFO", () => {
  assert.equal(isFailure({ level: "INFO", status_code: 503 }), true);
  assert.equal(isFailure({ error_code: "TimeoutError" }), true);
  assert.equal(isFailure({ status_code: 200 }), false);
});
test("parent ordering tolerates external parents and corrupt cycles", () => {
  const rows = orderedSpans([
    { span_id: "child", parent_span_id: "root" }, { span_id: "root", parent_span_id: "browser" },
    { span_id: "a", parent_span_id: "b" }, { span_id: "b", parent_span_id: "a" },
  ]);
  assert.deepEqual(rows.slice(0, 2).map(r => [r.span_id, r.depth]), [["root", 0], ["child", 1]]);
  assert.equal(rows.length, 4);
});
