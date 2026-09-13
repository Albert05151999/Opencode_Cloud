import { randomBytes, createHash } from "node:crypto";

// Dependency-free local hook for the pinned OpenCode chat.headers contract.
export default async () => {
  const assistants = new Map(), pending = new Map(), terminals = new Map();
  const limit = 1024;
  const valid = value => typeof value === "string" && /^[A-Za-z0-9_.:-]{1,128}$/.test(value);
  const key = (...parts) => JSON.stringify(parts);
  const bounded = (map, id, value) => { map.set(id, value); while (map.size > limit) map.delete(map.keys().next().value); };
  function complete(item, trace) {
    const id = key(item.session_id, item.message_id, item.call_id, item.part_id);
    if (terminals.has(id)) return;
    bounded(terminals, id, true);
    console.log("@@OPENCODE_CLOUD_EVENT@@" + JSON.stringify({
      ...item, trace_id: trace, span_id: createHash("sha256").update(key(trace, id)).digest("hex").slice(0,16),
      component: "sandbox", level: "INFO", event_kind: "span",
      // No invented parent: assistant->model_dispatch span linkage is unavailable.
    }));
  }
  function event({ event }) {
    const p = event?.properties || {};
    if (event?.type === "message.updated") {
      const info = p.info;
      if (!info || info.role !== "assistant" || !valid(info.sessionID) || !valid(info.id)) return;
      const match = /^msg_([0-9a-f]{32})$/.exec(info.parentID || "");
      if (!match || /^0+$/.test(match[1])) return;
      const id = key(info.sessionID, info.id);
      if (assistants.has(id) && assistants.get(id) !== match[1]) return;
      bounded(assistants, id, match[1]);
      for (const [partKey, item] of pending) {
        if (key(item.session_id, item.message_id) !== id) continue;
        pending.delete(partKey); complete(item, match[1]);
      }
      return;
    }
    if (event?.type === "session.deleted") {
      const sid = p.info?.id || p.sessionID;
      for (const map of [assistants, pending, terminals]) for (const id of map.keys()) if (JSON.parse(id)[0] === sid) map.delete(id);
      return;
    }
    if (event?.type !== "message.part.updated") return;
    const part = p.part, state = part?.state;
    if (part?.type !== "tool" || ![part.sessionID,part.messageID,part.id,part.callID,part.tool].every(valid)) return;
    if (!state || !["completed", "error"].includes(state.status)) return;
    const start = state.time?.start, end = state.time?.end;
    if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 || end < start || end-start > 86400000 || end > 8640000000000000) return;
    const item = { action: state.status === "completed" ? "tool_complete" : "tool_error",
      session_id: part.sessionID, message_id: part.messageID, part_id: part.id, call_id: part.callID,
      tool: part.tool, duration_ms: end-start, timestamp: new Date(end).toISOString(),
      start_time_ms: start, end_time_ms: end,
      ...(state.status === "error" ? { error_code: "ToolExecutionError" } : {}) };
    const trace = assistants.get(key(part.sessionID,part.messageID));
    if (trace) complete(item,trace);
    else bounded(pending,key(part.sessionID,part.messageID,part.callID,part.id),item);
  }

  return {
  event,
  dispose: async () => { assistants.clear(); pending.clear(); terminals.clear(); },
  "chat.headers": async (input, output) => {
    const session = input.sessionID;
    const message = input.message?.id;
    const valid = (value) => typeof value === "string" && /^[A-Za-z0-9_.:-]{1,128}$/.test(value);
    if (!valid(session)) return;
    output.headers["x-cloud-session-id"] = session;
    if (valid(message)) {
      output.headers["x-cloud-message-id"] = message;
      output.headers["x-litellm-trace-id"] = message;
    }
    // The managed web client intentionally gives its user message a trace-backed
    // ID.  The hook receives that exact UserMessage, so this stays message-local
    // under concurrent prompts and does not rely on process-global state.
    const managed = typeof message === "string" && /^msg_([0-9a-f]{32})$/.exec(message);
    const span = managed ? randomBytes(8).toString("hex") : null;
    if (managed) {
      output.headers.traceparent = `00-${managed[1]}-${span}-01`;
    }
    console.log("@@OPENCODE_CLOUD_EVENT@@" + JSON.stringify({timestamp: new Date().toISOString(), level: "INFO",
      component: "sandbox", action: "model_dispatch", event_kind: "instant",
      message_id: valid(message) ? message : null,
      session_id: session, logical_model: input.model?.id ?? null,
      trace_id: managed ? managed[1] : null, span_id: span}));
  },
};
};
