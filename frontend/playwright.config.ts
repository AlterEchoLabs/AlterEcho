import { defineConfig, devices } from "@playwright/test";

const buildIdentifier = "phase6-e2e";
const python = process.platform === "win32" ? ".venv-geo\\Scripts\\python.exe" : ".venv-geo/bin/python";
const webgl = { args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] };

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["line"]],
  use: { baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "desktop-1327", use: { ...devices["Desktop Chrome"], viewport: { width: 1327, height: 660 }, launchOptions: webgl } },
    { name: "desktop-wide", use: { ...devices["Desktop Chrome"], viewport: { width: 1680, height: 1000 }, launchOptions: webgl } },
    { name: "mobile-390", use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, launchOptions: webgl } },
  ],
  webServer: [
    {
      command: `${python} -m uvicorn app.main:app --host 127.0.0.1 --port 8100`,
      cwd: "../backend",
      env: { BUILD_IDENTIFIER: buildIdentifier, CORS_ORIGINS: "http://127.0.0.1:3100,http://localhost:3100" },
      url: "http://127.0.0.1:8100/api/health",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // Production build + server: exercises the shipped bundle and avoids clashing with a local `next dev`.
      command: `${process.platform === "win32" ? "npm.cmd" : "npm"} run build && ${process.platform === "win32" ? "npm.cmd" : "npm"} run start -- --hostname 127.0.0.1 --port 3100`,
      cwd: ".",
      env: { NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8100", NEXT_PUBLIC_BUILD_IDENTIFIER: buildIdentifier },
      url: "http://127.0.0.1:3100",
      reuseExistingServer: false,
      timeout: 300_000,
    },
  ],
});
