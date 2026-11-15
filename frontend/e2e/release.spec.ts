import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { writeFileSync } from "node:fs";
import path from "node:path";
import { openMenuIfCollapsed } from "./helpers";

const routes = ["/", "/method", "/sources", "/explore", "/report?site=earth-atacama-south&reference=mars-jezero&profile=terrain_analogy"];

test("release themes, accessibility, screenshots and navigation", async ({ page }, info) => {
  test.setTimeout(180_000);
  await page.emulateMedia({ reducedMotion: "reduce" });
  const failures: string[] = [];
  page.on("pageerror", (error) => failures.push(error.message));
  for (const theme of ["dark", "light"]) {
    await page.goto("/");
    await openMenuIfCollapsed(page);
    await page.getByLabel("Color theme").selectOption(theme);
    for (const [index, route] of routes.entries()) {
      await page.goto(route);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await expect(page.locator("main h1").first()).toBeVisible();
      if (route === "/") await expect(page.getByTestId("results-list")).toBeVisible();
      if (route.startsWith("/report")) await expect(page.getByText("97.90", { exact: false }).first()).toBeVisible();
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      await info.attach(`accessibility-${theme}-${index}`, { body: JSON.stringify(results.violations, null, 2), contentType: "application/json" });
      expect(results.violations.map(v => ({ id: v.id, targets: v.nodes.map(n => n.target) }))).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: info.outputPath(`${theme}-${index}.png`), fullPage: false });
    }
  }
  await openMenuIfCollapsed(page);
  await page.getByLabel("Color theme").selectOption("system");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByText("Skip to content", { exact: true })).toBeFocused();
  expect(failures).toEqual([]);
  writeFileSync(path.resolve(__dirname, `../../docs/browser-accessibility-${info.project.name}.json`), JSON.stringify({
    routes, themes: ["dark", "light"], viewport: info.project.use.viewport,
    violations: [], scope: "axe WCAG 2 A/AA and 2.1 AA; reduced motion; theme persistence and system changes; skip link; horizontal overflow",
  }, null, 2));
});

test("release performance under laptop CPU and network throttling", async ({ page }, info) => {
  if (info.project.name !== "desktop-1327") test.skip();
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 40, downloadThroughput: 1_125_000, uploadThroughput: 500_000 });
  const started = Date.now();
  await page.goto("/");
  await expect(page.getByTestId("results-list")).toBeVisible({ timeout: 30_000 });
  const elapsed = Date.now() - started;
  writeFileSync(path.resolve(__dirname, "../../docs/browser-performance.json"), JSON.stringify({ results_visible_ms: elapsed,
    cpu_slowdown: 4, latency_ms: 40, download_bytes_per_second: 1125000, runs: 1,
    limitation: "Single headless Chromium run with software rendering on this host, not a device benchmark or production service guarantee" }, null, 2));
  await info.attach("performance", { body: JSON.stringify({ results_visible_ms: elapsed, cpu_slowdown: 4, latency_ms: 40, download_bytes_per_second: 1125000 }), contentType: "application/json" });
  expect(elapsed).toBeLessThan(30_000);
});
