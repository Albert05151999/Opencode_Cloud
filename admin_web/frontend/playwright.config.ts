import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "../../test/admin_web/integration",
  use: {
    baseURL: process.env.WEB_TEST_BASE_URL || "http://127.0.0.1:18765",
    viewport: { width: 1440, height: 1000 },
  },
  workers: 1,
  reporter: "list",
});
