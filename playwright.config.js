import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/ui",
  fullyParallel: false,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:8011", trace: "retain-on-failure" },
  webServer: {
    command: "uv run python tests/ui_server.py",
    url: "http://127.0.0.1:8011/health",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
