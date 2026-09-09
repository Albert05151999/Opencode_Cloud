// Dependency-free local hook for the pinned OpenCode chat.headers contract.
export default async () => ({
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
    console.log(JSON.stringify({timestamp: new Date().toISOString(), level: "INFO",
      component: "sandbox", action: "model_request", session_id: session,
      message_id: valid(message) ? message : null,
      logical_model: input.model?.id ?? null}));
  },
});
