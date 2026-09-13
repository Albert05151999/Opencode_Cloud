import { test, expect } from "../../../admin_web/frontend/node_modules/@playwright/test/index.mjs";
const model = {
  id: "coding-fast",
  name: "Coding Fast",
  provider: "legacy",
  upstream_model: "coding-fast",
  legacy: true,
  enabled: true,
};
const draft = {
  name: "Code Agent",
  description: "你的云端代码助手",
  enabled: true,
  instructions: "Help with code.",
  allowed_model_ids: ["coding-fast"],
  default_model_id: "coding-fast",
  small_model_id: null,
  bindings: [],
};
const catalog = {
  revision: 1,
  models: { "coding-fast": model },
  agents: {
    "agent-code": {
      id: "agent-code",
      draft,
      active: 1,
      versions: [{ version: 1, config: draft }],
    },
  },
  resources: {},
  jobs: {},
  gateway_versions: [],
};
const loadCapacity = {
  known: true,
  admission_allowed: true,
  reasons: [],
  remaining_cpu: 6,
  remaining_memory_mb: 10000,
  cpu_usage_percent: 20,
  memory_available_mb: 12000,
  allocated_cpu: 1,
  allocated_memory_mb: 3000,
  reserved_cpu: 1,
  reserved_memory_mb: 1024,
  running_sandboxes: 1,
};

const loadReport = {
  id: "lt_browser",
  created_at: 1789110000,
  status: "completed",
  cleanup_status: "retained",
  summary: {
    users: 2,
    prepared: 2,
    submitted: 2,
    succeeded: 2,
    failed: 0,
    cancelled: 0,
    success_rate: 1,
    p50_ms: 100,
    p95_ms: 200,
    p99_ms: 200,
    successful_requests_per_second: 2,
    launch_spread_ms: 3,
    input_tokens: 20,
    output_tokens: 8,
  },
  by_agent: { "agent-code": { users: 2, succeeded: 2, p95_ms: 200 } },
  users: [
    {
      agent_id: "agent-code",
      username: "loadtest-browser-1",
      sandbox_id: "sbx_browser",
      session_id: "ses_browser",
      phase: "succeeded",
      storage_state: "retained",
      prepare_ms: 50,
      latency_ms: 100,
    },
  ],
};

test("load test selects existing Agents and submits user resource limits once", async ({
  page,
}) => {
  let body: any,
    calls = 0;
  await page.route("**/remote/cloud/capabilities", (r) =>
    r.fulfill({ json: { load_testing: true } }),
  );
  await page.route("**/remote/cloud/admin/load-tests/options", (r) =>
    r.fulfill({
      json: {
        agents: [
          {
            id: "agent-code",
            name: "Code",
            version: 1,
            model_id: "coding-fast",
          },
        ],
        max_users: 100,
        host_capacity: { cpu_count: 8, memory_mb: 16384 },
        prompt: "LOAD-TEST-OK",
      },
    }),
  );
  await page.route("**/remote/cloud/admin/load-tests?*", (r) =>
    r.fulfill({ json: { items: [], total: 0 } }),
  );
  await page.route("**/remote/cloud/admin/load-tests", (r) => {
    calls++;
    body = r.request().postDataJSON();
    return r.fulfill({ json: { id: "lt_browser", created: true } });
  });
  await page.route("**/remote/cloud/admin/load-tests/lt_browser", (r) =>
    r.fulfill({ json: loadReport }),
  );
  await page.goto("/admin");
  await page.getByRole("button", { name: "压测", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "开始压测", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("选择 agent-code", { exact: true }).check();
  await page.getByLabel("agent-code 用户数", { exact: true }).fill("2");
  await page.getByLabel("agent-code CPU", { exact: true }).fill("0.5");
  await page.getByLabel("agent-code 内存", { exact: true }).fill("1536");
  await expect(page.getByRole("status")).toContainText("2 个用户 / 2 个沙箱");
  await page.getByRole("button", { name: "开始压测", exact: true }).click();
  await expect(page.getByRole("region", { name: "压测报告" })).toBeVisible();
  expect(calls).toBe(1);
  expect(body.agents).toEqual([
    { agent_id: "agent-code", users: 2, cpu_limit: 0.5, memory_mb: 1536 },
  ]);
  expect(body.request_id.length).toBeGreaterThan(8);
});

test("load test report requires exact confirmation before destroying test users", async ({
  page,
}) => {
  let cleaned = false,
    confirmation: any;
  await page.route("**/remote/cloud/capabilities", (r) =>
    r.fulfill({ json: { load_testing: true } }),
  );
  await page.route("**/remote/cloud/admin/load-tests/options", (r) =>
    r.fulfill({ json: { agents: [], max_users: 100, host_capacity: {} } }),
  );
  await page.route("**/remote/cloud/admin/load-tests?*", (r) =>
    r.fulfill({ json: { items: [loadReport], total: 1 } }),
  );
  await page.route("**/remote/cloud/admin/load-tests/lt_browser", (r) =>
    r.fulfill({
      json: { ...loadReport, cleanup_status: cleaned ? "cleaned" : "retained" },
    }),
  );
  await page.route(
    "**/remote/cloud/admin/load-tests/lt_browser/cleanup",
    (r) => {
      confirmation = r.request().postDataJSON();
      cleaned = true;
      return r.fulfill({ json: { cleanup_status: "cleaning" } });
    },
  );
  await page.goto("/admin");
  await page.getByRole("button", { name: "压测", exact: true }).click();
  await page.getByRole("button", { name: /lt_browser/ }).click();
  const destroy = page.getByRole("button", {
    name: "销毁测试沙箱和用户数据",
    exact: true,
  });
  await expect(destroy).toBeDisabled();
  await page
    .getByLabel("输入完整测试 ID 确认", { exact: true })
    .fill("lt_browser");
  await destroy.click();
  expect(confirmation).toEqual({ confirmation: "lt_browser" });
  await expect(
    page.getByText("数据状态：已清理", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("region", { name: "压测报告" })).toContainText(
    "成功率 100%",
  );
});

test("load test blocks over-budget and unknown capacity and shows user allowance", async ({
  page,
}) => {
  let known = true;
  await page.route("**/remote/cloud/capabilities", (r) =>
    r.fulfill({ json: { load_testing: true } }),
  );
  await page.route("**/remote/cloud/admin/load-tests/options", (r) =>
    r.fulfill({
      json: {
        agents: [
          {
            id: "agent-code",
            name: "Code",
            version: 1,
            model_id: "coding-fast",
          },
        ],
        max_users: 100,
        host_capacity: {},
      },
    }),
  );
  await page.route("**/remote/cloud/admin/load-tests?*", (r) =>
    r.fulfill({ json: { items: [], total: 0 } }),
  );
  await page.route("**/remote/cloud/admin/load-tests/capacity", (r) =>
    r.fulfill({
      json: {
        ...loadCapacity,
        known,
        sampled_at: Date.now() / 1000,
        remaining_cpu: 1,
        remaining_memory_mb: 1024,
      },
    }),
  );
  await page.goto("/admin");
  await page.getByRole("button", { name: "压测", exact: true }).click();
  await page.getByLabel("选择 agent-code", { exact: true }).check();
  await page.getByLabel("agent-code 用户数", { exact: true }).fill("2");
  await expect(
    page.getByRole("button", { name: "开始压测", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText("agent-code 在其他行不变时最多 1 个用户。"),
  ).toBeVisible();
  await page.getByLabel("agent-code 用户数", { exact: true }).fill("1");
  await expect(
    page.getByRole("button", { name: "开始压测", exact: true }),
  ).toBeEnabled();
  known = false;
  await page.getByRole("button", { name: "刷新压测", exact: true }).click();
  await expect(
    page.getByText("资源状态未知或已过期，暂不能开始压测。"),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "开始压测", exact: true }),
  ).toBeDisabled();
});

test("old server capabilities explain unavailable operations", async ({
  page,
}) => {
  await page.route("**/remote/cloud/capabilities", (r) =>
    r.fulfill({ json: { version: "0.2.2", management: true } }),
  );
  await page.goto("/admin");
  await page.getByRole("button", { name: "沙箱", exact: true }).click();
  await expect(
    page.getByText("此服务器尚不支持这个管理功能。", { exact: false }),
  ).toBeVisible();
  await expect(page.getByLabel("搜索沙箱")).toHaveCount(0);
});

test("restoring an imported template is an explicit unpublished action", async ({
  page,
}) => {
  let submitted: any;
  await page.route("**/remote/cloud/admin/agent-templates", (r) =>
    r.fulfill({
      json: [{ id: "tpl_browser", name: "Imported Agent", config: draft }],
    }),
  );
  await page.route(
    "**/remote/cloud/admin/agent-templates/tpl_browser/restore",
    (r) => {
      submitted = r.request().postDataJSON();
      return r.fulfill({
        json: { agent_id: "restored-browser", published: false },
      });
    },
  );
  await page.goto("/admin");
  await page.getByRole("button", { name: "导入导出", exact: true }).click();
  await page
    .getByRole("combobox", { name: "待恢复配置", exact: true })
    .selectOption("tpl_browser");
  expect(submitted).toBeUndefined();
  await page
    .getByLabel("新的 Agent ID", { exact: true })
    .fill("restored-browser");
  await page.getByRole("button", { name: "恢复为新的 Agent 草稿" }).click();
  expect(submitted).toEqual({
    agent_id: "restored-browser",
    models: {},
    resources: {},
  });
  await expect(page.getByRole("status")).toContainText("草稿已创建");
});

test("resource import previews before committing global drafts", async ({
  page,
}) => {
  let committed: any;
  await page.route("**/remote/cloud/admin/imports/preview", (r) =>
    r.fulfill({
      json: {
        preview_id: "imp_browser",
        warnings: [],
        items: [
          {
            key: "0",
            id: "docs",
            name: "docs",
            kind: "mcp",
            data: { type: "remote", url: "https://example.org/mcp" },
            files: [],
          },
        ],
      },
    }),
  );
  await page.route("**/remote/cloud/admin/imports/imp_browser/commit", (r) => {
    committed = r.request().postDataJSON();
    return r.fulfill({
      json: {
        imported: [{ id: "docs" }],
        published: false,
        assigned_agents: [],
      },
    });
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "导入导出", exact: true }).click();
  await page
    .getByLabel("导入资源文件", { exact: true })
    .setInputFiles({
      name: "opencode.json",
      mimeType: "application/json",
      buffer: Buffer.from("{}"),
    });
  await expect(page.getByRole("heading", { name: "导入预览" })).toBeVisible();
  expect(committed).toBeUndefined();
  await page.getByLabel("目标 ID docs").fill("docs-copy");
  await page.getByRole("button", { name: "导入到全局资源池草稿" }).click();
  expect(committed).toEqual({
    selections: [{ key: "0", target_id: "docs-copy", replace: false }],
  });
  await expect(page.getByRole("status")).toContainText("全局草稿");
});

test("provider template and draft test preserve unpublished form", async ({
  page,
}) => {
  let tested: any;
  await page.route("**/remote/cloud/admin/provider-templates", (r) =>
    r.fulfill({
      json: [
        {
          id: "demo",
          name: "Demo Provider",
          provider: "openai-compatible",
          base_url: "https://example.org/v1",
          notes: "Test template",
          docs: "https://example.org",
        },
      ],
    }),
  );
  await page.route("**/remote/cloud/admin/models/test-draft", (r) => {
    tested = r.request().postDataJSON();
    return r.fulfill({ json: { ok: true, published: false } });
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "新建", exact: true }).click();
  await page.getByLabel("厂商模板", { exact: true }).selectOption("demo");
  await page
    .getByRole("button", { name: "测试当前表单（不保存、不发布）" })
    .click();
  expect(tested.model.base_url).toBe("https://example.org/v1");
  await expect(page.getByRole("status")).toContainText("当前表单测试通过");
});
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const native = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      if (input === "/remote/event") {
        const stream = new ReadableStream({
          start(c) {
            (window as any).__events = c;
            c.enqueue(
              new TextEncoder().encode(
                'data: {"type":"server.connected","properties":{}}\n\n',
              ),
            );
          },
        });
        return new Response(stream, {
          headers: { "content-type": "text/event-stream" },
        });
      }
      return native(input, init);
    };
  });
  await page.route("**/remote/**", async (route) => {
    const url = new URL(route.request().url()),
      p = url.pathname.replace("/remote", "");
    let data: any = {};
    if (p === "/cloud/admin/load-tests/capacity")
      data = { ...loadCapacity, sampled_at: Date.now() / 1000 };
    else if (p === "/cloud/capabilities")
      data = {
        sandbox_operations: true,
        resource_transfer: { version: 2 },
        provider_templates: true,
      };
    else if (p === "/cloud/agents")
      data = [{ id: "agent-code", version: 1, ...draft }];
    else if (p === "/cloud/models") data = [model];
    else if (p === "/cloud/admin/catalog") data = catalog;
    else if (p === "/session" && route.request().method() === "GET") data = [];
    else if (p === "/session" && route.request().method() === "POST")
      data = { id: "ses_browser" };
    else if (p.endsWith("/message")) data = [];
    else if (p === "/question" || p === "/permission") data = [];
    else data = { ok: true };
    await route.fulfill({ json: data });
  });
});
test("chat is usable and submits a prompt once", async ({ page }) => {
  let submissions = 0;
  page.on("request", (r) => {
    if (r.url().endsWith("/prompt_async")) submissions++;
  });
  await page.goto("/chat");
  await expect(page.getByText("让想法，在云端发生。")).toBeVisible();
  await expect(page.getByLabel("选择模型")).toHaveValue("coding-fast");
  await page.screenshot({
    path: "../../artifacts/admin_web/screenshots/chat-desktop.png",
    fullPage: true,
  });
  await page.getByLabel("消息", { exact: true }).fill("Calculate 1 + 1");
  await page.getByTitle("发送", { exact: true }).click();
  await expect.poll(() => submissions).toBe(1);
  await page.evaluate(() => {
    const c = (window as any).__events;
    for (const event of [
      {
        type: "message.updated",
        properties: {
          info: { id: "msg_a", sessionID: "ses_browser", role: "assistant" },
        },
      },
      {
        type: "message.part.updated",
        properties: {
          part: {
            id: "p",
            messageID: "msg_a",
            sessionID: "ses_browser",
            type: "text",
            text: "The answer is **2**.",
          },
        },
      },
    ])
      c.enqueue(
        new TextEncoder().encode("data: " + JSON.stringify(event) + "\n\n"),
      );
  });
  await expect(page.getByText("The answer is")).toBeVisible();
  expect(submissions).toBe(1);
});
test("admin saves MCP through the API and preserves draft semantics", async ({
  page,
}) => {
  let body: any;
  await page.route(
    "**/remote/cloud/admin/resources/test-mcp",
    async (route) => {
      body = route.request().postDataJSON();
      await route.fulfill({ json: { ok: true } });
    },
  );
  await page.goto("/admin");
  await page.getByRole("button", { name: "MCP", exact: true }).click();
  await page.getByRole("button", { name: "新建", exact: true }).click();
  await page.getByLabel("稳定 ID").fill("test-mcp");
  await page.getByLabel("名称（字母、数字、横线）").fill("test-mcp");
  await page.getByLabel("服务 URL").fill("https://mcp.example/api");
  await page.screenshot({
    path: "../../artifacts/admin_web/screenshots/mcp-editor.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "保存到服务器" }).click();
  await expect(
    page.getByText("草稿已保存到服务器；发布后才生效"),
  ).toBeVisible();
  expect(body.resource.data.oauth).toBe(false);
  expect(body.resource.owner).toBe(null);
});
test("Agent editor exposes explicit model selection and mobile layout", async ({
  page,
}) => {
  await page.goto("/admin");
  await page.getByRole("button", { name: "Agents", exact: true }).click();
  await page.getByRole("button", { name: "配置 Agent" }).click();
  await expect(page.getByText("选择可用模型")).toBeVisible();
  await expect(page.getByLabel("默认模型", { exact: true })).toHaveValue(
    "coding-fast",
  );
  await page.screenshot({
    path: "../../artifacts/admin_web/screenshots/agent-editor.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/chat");
  await expect(page.getByLabel("消息", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../../artifacts/admin_web/screenshots/chat-mobile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "会话列表", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "新对话", exact: true }),
  ).toBeVisible();
});

test("refresh restores the selected session without submitting again", async ({
  page,
}) => {
  let submissions = 0;
  page.on("request", (r) => {
    if (r.url().endsWith("/prompt_async")) submissions++;
  });
  await page.addInitScript(() =>
    localStorage.setItem("session:agent-code:local-demo", "ses_saved"),
  );
  await page.route("**/remote/session/ses_saved/message", (r) =>
    r.fulfill({
      json: [
        {
          info: { id: "msg_saved", role: "assistant", sessionID: "ses_saved" },
          parts: [
            { id: "p_saved", type: "text", text: "Saved server history" },
          ],
        },
      ],
    }),
  );
  await page.route("**/remote/session/status", (r) =>
    r.fulfill({ json: { ses_saved: { type: "busy" } } }),
  );
  await page.goto("/chat");
  await expect(page.getByText("Saved server history")).toBeVisible();
  await expect(page.getByTitle("停止生成")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Saved server history")).toBeVisible();
  expect(submissions).toBe(0);
});

test("permission and question answers use native public endpoints", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("session:agent-code:local-demo", "ses_saved"),
  );
  await page.route("**/remote/permission", (r) =>
    r.fulfill({
      json: [{ id: "per_test", sessionID: "ses_saved", permission: "bash" }],
    }),
  );
  await page.route("**/remote/question", (r) =>
    r.fulfill({
      json: [
        {
          id: "que_test",
          sessionID: "ses_saved",
          questions: [
            {
              question: "选择输出格式",
              options: [{ label: "CSV", description: "表格" }],
            },
          ],
        },
      ],
    }),
  );
  let permission: any, question: any;
  await page.route("**/remote/permission/per_test/reply", (r) => {
    permission = r.request().postDataJSON();
    return r.fulfill({ json: true });
  });
  await page.route("**/remote/question/que_test/reply", (r) => {
    question = r.request().postDataJSON();
    return r.fulfill({ json: true });
  });
  await page.goto("/chat");
  await page.getByRole("button", { name: "允许一次", exact: true }).click();
  expect(permission).toEqual({ reply: "once" });
  await page.getByPlaceholder("或输入回答").fill("CSV");
  await page.getByRole("button", { name: "提交回答", exact: true }).click();
  expect(question).toEqual({ answers: [["CSV"]] });
});

test("model references open locally without a connection error or catalog reload", async ({
  page,
}) => {
  let loads = 0;
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/remote/cloud/admin/catalog*", (r) => {
    loads++;
    return r.fulfill({
      json: {
        ...catalog,
        models: { "coding-fast": { ...model, references: ["agent-code"] } },
      },
    });
  });
  await page.goto("/admin");
  await expect(
    page.getByRole("button", { name: "引用关系", exact: true }),
  ).toBeVisible();
  const initialLoads = loads;
  await page.getByRole("button", { name: "引用关系", exact: true }).click();
  await expect(page.locator(".json-view")).toContainText("agent-code");
  await expect(page.locator(".notice.error")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "检查连接", exact: true }),
  ).toHaveCount(0);
  expect(loads).toBe(initialLoads);
  expect(errors).toEqual([]);
});

test("reasoning shows one clipped line and expands on demand across history reloads", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("session:agent-code:local-demo", "ses_saved"),
  );
  const first = "First reasoning line ".repeat(30),
    second = "Second reasoning line stays collapsed";
  await page.route("**/remote/session/ses_saved/message", (r) =>
    r.fulfill({
      json: [
        {
          info: { id: "msg_saved", role: "assistant", sessionID: "ses_saved" },
          parts: [
            { id: "reason", type: "reasoning", text: first + "\n" + second },
            { id: "answer", type: "text", text: "Final answer" },
          ],
        },
      ],
    }),
  );
  await page.goto("/chat");
  const reasoning = page.locator(".reasoning"),
    preview = reasoning.locator(".reasoning-preview");
  await expect(preview).toContainText("First reasoning line");
  await expect(reasoning.locator(".reasoning-content")).toBeHidden();
  expect(await preview.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(
    true,
  );
  await reasoning.locator("summary").click();
  await expect(reasoning.locator(".reasoning-content")).toContainText(second);
  await expect(reasoning.locator(".reasoning-content")).toBeVisible();
  await reasoning.locator("summary").click();
  await expect(reasoning.locator(".reasoning-content")).toBeHidden();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(preview).toBeVisible();
  await expect(reasoning.locator(".reasoning-content")).toBeHidden();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("file drawer refreshes after idle and manually, and ignores another session", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("session:agent-code:local-demo", "ses_saved"),
  );
  let entries: any[] = [{ name: "test.txt", type: "file", size: 0 }],
    loads = 0;
  await page.route("**/remote/cloud/files/list?*", (r) => {
    loads++;
    return r.fulfill({ json: { entries } });
  });
  await page.goto("/chat");
  await page.getByTitle("查看产物").click();
  await expect(page.locator(".drawer")).toContainText("test.txt");
  entries = [...entries, { name: "report.txt", type: "file", size: 42 }];
  await page.evaluate(() => {
    (window as any).__events.enqueue(
      new TextEncoder().encode(
        "data: " +
          JSON.stringify({
            type: "session.idle",
            properties: { sessionID: "ses_saved" },
          }) +
          "\n\n",
      ),
    );
  });
  await expect(page.locator(".drawer")).toContainText("report.txt");
  entries = [...entries, { name: "manual.txt", type: "file", size: 5 }];
  await page.getByRole("button", { name: "刷新文件", exact: true }).click();
  await expect(page.locator(".drawer")).toContainText("manual.txt");
  const previous = loads;
  await page.evaluate(() => {
    (window as any).__events.enqueue(
      new TextEncoder().encode(
        "data: " +
          JSON.stringify({
            type: "session.idle",
            properties: { sessionID: "ses_other" },
          }) +
          "\n\n",
      ),
    );
  });
  await page.getByRole("button", { name: "新对话", exact: true }).click();
  await expect(page.locator(".drawer")).toHaveCount(0);
  expect(loads).toBe(previous);
});

test("configuration viewers distinguish saved configuration and live form JSON", async ({
  page,
}) => {
  await page.route("**/remote/cloud/admin/config-preview", (r) =>
    r.fulfill({
      json: {
        scope: "resource-library",
        models: { sample: { api_key: "must-not-show" } },
        resources: {},
        active_gateway: { model_list: [] },
        gateway_version: 1,
      },
    }),
  );
  await page.goto("/admin");
  await page.getByRole("button", { name: "全局 JSON", exact: true }).click();
  await expect(
    page.getByText("全局模型资源库 · 已保存", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".modal")).not.toContainText("must-not-show");
  await page.locator(".modal > .section-heading .icon").click();
  await page.getByRole("button", { name: "MCP", exact: true }).click();
  await page.getByRole("button", { name: "新建", exact: true }).click();
  await page.getByLabel("名称（字母、数字、横线）").fill("example-mcp");
  await page.getByLabel("服务 URL").fill("https://mcp.example/tools");
  const json = page.locator(".form-config-preview .json-view");
  await expect(json).toContainText("example-mcp");
  await expect(json).toContainText("https://mcp.example/tools");
  await page.getByLabel("服务 URL").fill("https://mcp.example/changed");
  await expect(json).toContainText("/changed");
});

test("Agent form JSON comes from the server compiler and updates without saving", async ({
  page,
}) => {
  let saves = 0;
  page.on("request", (r) => {
    if (r.method() === "PUT") saves++;
  });
  await page.route(
    "**/remote/cloud/admin/agents/agent-code/config-preview",
    (r) => {
      const cfg = r.request().postDataJSON().config;
      return r.fulfill({
        json: {
          opencode: {
            model: "cloud-model-gateway/" + cfg.default_model_id,
            small_model: cfg.small_model_id,
          },
          sources: [],
        },
      });
    },
  );
  await page.goto("/admin");
  await page.getByRole("button", { name: "Agents", exact: true }).click();
  await page.getByRole("button", { name: "配置 Agent", exact: true }).click();
  await expect(page.locator(".form-config-preview .json-view")).toContainText(
    "cloud-model-gateway/coding-fast",
  );
  await page
    .getByLabel("小模型（可选）", { exact: true })
    .selectOption("coding-fast");
  await expect(page.locator(".form-config-preview .json-view")).toContainText(
    '"small_model": "coding-fast"',
  );
  expect(saves).toBe(0);
});

test("sandbox search and restart use the operations API", async ({ page }) => {
  const row = {
    sandbox_id: "sbx_ui",
    container_id: "container_ui",
    agent_id: "agent-code",
    username: "alice",
    status: "ready",
    desired_state: "running",
    last_active_at: "2026-09-10",
  };
  let submitted: any = null;
  await page.route("**/remote/cloud/admin/sandboxes?*", async (route) => {
    const q = new URL(route.request().url()).searchParams.get("q") || "";
    await route.fulfill({
      json: {
        items: "sbx_ui container_ui alice".includes(q) ? [row] : [],
        total: "sbx_ui container_ui alice".includes(q) ? 1 : 0,
      },
    });
  });
  await page.route(
    "**/remote/cloud/admin/sandboxes/sbx_ui/restart",
    async (route) => {
      submitted = route.request().postDataJSON();
      await route.fulfill({ json: { job_id: "job_ui" } });
    },
  );
  await page.route("**/remote/cloud/admin/jobs/job_ui", async (route) =>
    route.fulfill({ json: { id: "job_ui", status: "succeeded" } }),
  );
  await page.goto("/admin");
  await page.getByRole("button", { name: "沙箱", exact: true }).click();
  await page.getByLabel("搜索沙箱").fill("alice");
  await expect(page.getByText("sbx_ui", { exact: true })).toBeVisible();
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "重启", exact: true }).click();
  await expect.poll(() => submitted?.request_id?.length).toBe(36);
  await expect(page.getByRole("status")).toContainText("succeeded");
});

test("logs filter by module and job and open correlated trace", async ({ page }) => {
  await page.route("**/remote/cloud/logs/modules", r => r.fulfill({json: {items: ["operations"]}}));
  await page.route("**/remote/cloud/logs?*", r => {
    const url = new URL(r.request().url());
    expect(url.searchParams.get("module")).toBe("operations");
    expect(url.searchParams.get("job_id")).toBe("job_demo");
    return r.fulfill({json: {items: [{module: "operations", action: "release.completed", timestamp: "2026-09-12", trace_id: "trace_demo", job_id: "job_demo", level: "INFO"}]}});
  });
  await page.route("**/remote/cloud/traces/trace_demo", r => r.fulfill({json: {trace_id: "trace_demo", spans: [{module: "operations", span_id: "span_demo", action: "release.completed"}], events: []}}));
  await page.goto("/admin");
  await page.getByRole("button", {name: "日志与调用链", exact: true}).click();
  await page.getByLabel("日志模块").selectOption("operations");
  await page.getByLabel("任务 ID", {exact: true}).fill("job_demo");
  await page.getByRole("button", {name: "查询", exact: true}).click();
  await page.getByRole("button", {name: "查看调用链"}).click();
  await expect(page.getByRole("region", {name: "调用链详情"})).toContainText("span_demo");
  await expect(page.getByRole("region", {name: "调用链详情"})).toContainText("未知 / 未提供");
});
