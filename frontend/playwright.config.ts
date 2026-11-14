import { defineConfig, devices } from "@playwright/test";

const buildIdentifier = "phase5-e2e";

export default defineConfig({
  testDir: "./e2e",
  timeout: 35_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  reporter: [["line"]],
  use: { baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 768 }, acceptDownloads: true } }],
  webServer: [
    {
      command: ".venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100",
      cwd: "../backend",
      env: { BUILD_IDENTIFIER: buildIdentifier, CORS_ORIGINS: "http://127.0.0.1:3100,http://localhost:3100" },
      url: "http://127.0.0.1:8100/api/health",
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "npm.cmd run dev -- --hostname 127.0.0.1 --port 3100",
      cwd: ".",
      env: { NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8100", NEXT_PUBLIC_BUILD_IDENTIFIER: buildIdentifier },
      url: "http://127.0.0.1:3100",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
