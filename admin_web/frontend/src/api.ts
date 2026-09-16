import { traceHeaders } from "./tracing";
export type Dict = Record<string, any>;
let csrf = "";
export async function bootstrap() {
  const data = await request("/local/bootstrap");
  csrf = data.csrf;
  return data;
}
export async function request(
  path: string,
  method = "GET",
  body?: unknown,
  headers: Record<string, string> = {},
) {
  const form = body instanceof FormData;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 130_000);
  try {
  const response = await fetch(path, {
    signal: controller.signal,
    method,
    headers: {
      ...(path.startsWith("/remote/") ? traceHeaders() : {}),
      ...(form
        ? {}
        : body !== undefined
          ? { "Content-Type": "application/json" }
          : {}),
      ...(method === "GET" ? {} : { "X-Local-CSRF": csrf }),
      ...headers,
    },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
  });
  const text = await response.text();
  let result: any;
  try {
    result = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(`服务器返回了无法解析的响应（HTTP ${response.status}），请检查服务状态后重试。`);
  }
  if (!response.ok) {
    const detail = typeof result.detail === 'string' ? result.detail
      : Array.isArray(result.detail) ? result.detail.map((item: Dict) => `${(item.loc || []).filter((v: string) => v !== 'body').join(' / ')}：${item.msg || '填写有误'}`).join('；')
      : `请求失败 (${response.status})`;
    const hint = response.status === 409 ? ' 配置可能已更新或有任务正在执行，请刷新核对后重试；当前表单已保留。' : '';
    throw new Error(detail + hint);
  }
  return result;
  } catch (error) {
    if (controller.signal.aborted) throw new Error('请求超时。写入操作可能仍在服务器执行，请先刷新记录确认结果，再决定是否重试。');
    if (error instanceof TypeError) throw new Error('无法连接本地服务，请检查 admin-web 是否仍在运行，然后重试。');
    throw error;
  } finally { clearTimeout(timer); }
}
export const remote = (
  path: string,
  method = "GET",
  body?: unknown,
  headers?: Record<string, string>,
) => request("/remote" + path, method, body, headers);
export function routeHeaders(agent: string, user: string) {
  return { "X-Cloud-Agent-ID": agent, "X-Cloud-Username": user };
}
export async function streamEvents(
  headers: Record<string, string>,
  signal: AbortSignal,
  onEvent: (e: Dict) => void,
) {
  const response = await fetch("/remote/event", {
    headers: { ...traceHeaders(), ...headers, Accept: "text/event-stream" },
    signal,
  });
  if (
    !response.ok ||
    !response.headers.get("content-type")?.startsWith("text/event-stream")
  )
    throw Error(`流连接失败 (${response.status})`);
  const reader = response.body!.getReader(),
    decoder = new TextDecoder();
  let buffer = "",
    data: string[] = [];
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) throw Error("事件流已断开");
      buffer += decoder.decode(chunk.value, { stream: true });
      if (buffer.length > 2 * 1024 * 1024) throw Error("事件帧过大");
      let end;
      while ((end = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, end).replace(/\r$/, "");
        buffer = buffer.slice(end + 1);
        if (line === "") {
          if (data.length) {
            onEvent(JSON.parse(data.join("\n")));
            data = [];
          }
        } else if (line.startsWith("data:"))
          data.push(line.slice(5).replace(/^ /, ""));
      }
    }
  } finally {
    reader.releaseLock();
    await response.body?.cancel().catch(() => {});
  }
}
export async function download(path: string, name: string) {
  const response = await fetch("/remote" + path, { headers: traceHeaders() });
  if (!response.ok) throw Error("下载失败");
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
