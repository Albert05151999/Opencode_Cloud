#!/usr/bin/env node
// Real LAN acceptance: no page.route, request interception, or synthetic responses.
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { chromium } from "../../admin_web/frontend/node_modules/@playwright/test/index.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const target = (process.argv[2] || "http://192.168.1.152:18080").replace(/\/$/, "");
const token = process.env.ADMIN_WEB_ACCEPTANCE_TOKEN;
const port = Number(process.env.ADMIN_WEB_ACCEPTANCE_PORT || 18766);
const python = process.env.ADMIN_WEB_PYTHON || path.join(root, ".venv-controller/bin/python");
const releaseRoot = process.env.ADMIN_WEB_RELEASE_ROOT
  ? path.resolve(process.env.ADMIN_WEB_RELEASE_ROOT)
  : "";
if (!token) throw new Error("Set ADMIN_WEB_ACCEPTANCE_TOKEN to the deployed admin token");

const state = await mkdtemp(path.join(os.tmpdir(), "opencode-admin-smoke-"));
const local = `http://127.0.0.1:${port}`;
const command = releaseRoot ? "sh" : python;
const args = releaseRoot
  ? [path.join(releaseRoot, "admin_web/scripts/start.sh")]
  : ["admin_web/scripts/start.py", "--no-browser", "--port", String(port)];
const companion = spawn(
  command,
  args,
  {
    cwd: releaseRoot || root,
    env: {
      ...process.env,
      ...(releaseRoot ? { ADMIN_WEB_ROOT: releaseRoot } : {}),
      ADMIN_WEB_DATA_ROOT: state,
      ADMIN_WEB_GATEWAY_URL: target,
      ADMIN_WEB_PORT: String(port),
    },
    stdio: ["ignore", "pipe", "pipe"],
  },
);
let companionLog = "";
companion.stdout.on("data", (chunk) => (companionLog += chunk));
companion.stderr.on("data", (chunk) => (companionLog += chunk));

async function waitForCompanion() {
  for (let attempt = 0; attempt < 50; attempt++) {
    if (companion.exitCode !== null)
      throw new Error(`Local companion exited ${companion.exitCode}:\n${companionLog}`);
    try {
      const response = await fetch(`${local}/local/bootstrap`);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`Local companion did not start:\n${companionLog}`);
}

function check(condition, message) {
  if (!condition) throw new Error(message);
}

let browser;
try {
  await waitForCompanion();
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const browserErrors = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await page.goto(`${local}/admin`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "连接设置", exact: true }).click();
  await page.getByLabel("API 地址").fill(target);
  await page.getByLabel("管理员凭据").fill(token);
  await page.getByRole("button", { name: "保存连接", exact: true }).click();
  await page.getByText("连接已保存", { exact: true }).waitFor();

  const connectionResponse = page.waitForResponse(
    (response) => response.url().endsWith("/local/connection/test"),
  );
  await page.getByRole("button", { name: "测试已保存的连接", exact: true }).click();
  const connection = await (await connectionResponse).json();
  check(connection.ready, "Real gateway readiness payload is missing");
  check(connection.capabilities, "Real gateway capabilities payload is missing");
  await page.getByText("就绪检查和管理能力检查通过", { exact: true }).waitFor();

  const modulesResponse = page.waitForResponse((response) =>
    response.url().includes("/remote/cloud/logs/modules"),
  );
  await page.getByRole("button", { name: "日志与调用链", exact: true }).click();
  const modules = (await (await modulesResponse).json()).items || [];
  check(modules.length > 0, "Real server returned no observable modules");
  const logModule = "api_gateway";
  check(modules.includes(logModule), "Real server returned no api_gateway logs module");
  await page.getByLabel("日志模块").selectOption(logModule);

  const logsResponse = page.waitForResponse((response) =>
    response.url().includes("/remote/cloud/logs?"),
  );
  await page.getByRole("button", { name: "查询", exact: true }).click();
  const logs = (await (await logsResponse).json()).items || [];
  check(logs.length > 0, `Real server returned no logs for module ${logModule}`);
  const traced = logs.find((entry) => entry.trace_id);
  check(traced, `Real logs for module ${logModule} contain no trace_id`);

  await page.getByLabel("追踪 ID").fill(traced.trace_id);
  const traceResponse = page.waitForResponse((response) =>
    response.url().includes(`/remote/cloud/traces/${encodeURIComponent(traced.trace_id)}`),
  );
  await page.getByRole("button", { name: "查询", exact: true }).click();
  const trace = await (await traceResponse).json();
  check(
    (trace.spans || []).length + (trace.events || []).length > 0,
    "Real trace has neither spans nor events",
  );
  await page.getByRole("region", { name: "调用链详情" }).waitFor();
  check(browserErrors.length === 0, `Browser errors: ${browserErrors.join("; ")}`);

  const evidence = {
    target,
    client_source: releaseRoot || root,
    checked_at: new Date().toISOString(),
    ready: connection.ready,
    capabilities: connection.capabilities,
    modules,
    queried_module: logModule,
    log_count: logs.length,
    trace_id: traced.trace_id,
    trace_span_count: (trace.spans || []).length,
    trace_event_count: (trace.events || []).length,
  };
  const artifactDir = path.join(root, "artifacts", "admin_web");
  await mkdir(artifactDir, { recursive: true });
  await page.screenshot({ path: path.join(artifactDir, "real-lan-smoke.png"), fullPage: true });
  await writeFile(
    path.join(artifactDir, "real-lan-smoke.json"),
    JSON.stringify(evidence, null, 2) + "\n",
  );
  console.log(JSON.stringify(evidence, null, 2));
} finally {
  if (browser) await browser.close();
  companion.kill("SIGTERM");
  await rm(state, { recursive: true, force: true });
}
