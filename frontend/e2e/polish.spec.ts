import { expect, test, type Page } from "@playwright/test";
import { openMenuIfCollapsed, pickReference, setDetail } from "./helpers";

/* Demo polish: first viewport, Simple vs Detailed, sticky header, map fallback, themes, mobile menu,
   URL state with back/forward, keyboard-only use and reduced motion. Screenshots are attached to each test's report. */

const GIBS = /gibs\.earthdata\.nasa\.gov/;
const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1000) < 960;

async function openAtlas(page: Page, path = "/") {
  await page.goto(path);
  await expect(page.getByTestId("results-list")).toBeVisible();
}

async function plateLoaded(page: Page) {
  const image = page.getByTestId("study-plate").getByRole("img").first();
  await expect.poll(() => image.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth), { timeout: 30_000 }).toBe(1000);
}

async function shot(page: Page, name: string, info: { outputPath: (n: string) => string; attach: (n: string, o: { path: string; contentType: string }) => Promise<void> }) {
  const file = info.outputPath(`${name}.png`);
  await page.screenshot({ path: file });
  await info.attach(name, { path: file, contentType: "image/png" });
}

test("atlas opens on Jezero · terrain shape · Simple, with the leading result and its image", async ({ page }, info) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openAtlas(page);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Which Earth terrain is closest to Jezero Crater?");
  await expect(page.getByTestId("reference-picker")).toContainText("Jezero Crater");
  await expect(page.getByTestId("mode-terrain")).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("detail-toggle").getByRole("radio", { name: "Simple", includeHidden: true })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("results-list").getByRole("button")).toHaveCount(3);
  const first = page.getByTestId("results-list").getByRole("button").first();
  await expect(first).toHaveAttribute("aria-current", "true");
  await expect(page.getByTestId("verdict")).toBeVisible();
  await plateLoaded(page);
  // Decision-level only: no tables, formulas, histograms or exports in Simple.
  for (const id of ["calc-table", "ordinary-chart", "download-json", "site-search", "plate-legend"]) await expect(page.getByTestId(id)).toHaveCount(0);
  await expect(page.locator(".katex")).toHaveCount(0);
  if (!isMobile(page)) {
    // The answer is in the first viewport on a laptop screen.
    const box = await page.getByTestId("verdict").boundingBox();
    expect(box!.y + box!.height).toBeLessThan(page.viewportSize()!.height);
  }
  await expect(page.getByTestId("team-members")).toContainText("Sarbagya Acharya");
  for (const name of ["Bikash Pandey", "Saurav Shah", "Neharika Acharya"]) await expect(page.getByTestId("team-members")).toContainText(name);
  await shot(page, "atlas-simple", info);
});

test("Detailed shows the whole calculation and switching back keeps reference, site and comparison", async ({ page }, info) => {
  await openAtlas(page, "/?reference=mars-jezero&site=earth-atacama-south");
  await setDetail(page, "Detailed");
  await expect(page.getByTestId("full-evidence")).toBeVisible();
  await expect(page.getByTestId("calc-table")).toContainText("Slope distribution");
  await expect(page.getByTestId("score-range")).toBeVisible();
  await expect(page.getByTestId("ordinary-chart")).toBeVisible();
  await expect(page.getByTestId("coverage-text")).toContainText("Experimental");
  await expect(page.getByTestId("plate-legend")).toContainText("Product");
  await expect(page.getByTestId("download-json")).toBeVisible();
  await expect(page.getByTestId("group-label")).toHaveCount(2);
  expect(new URL(page.url()).searchParams.get("view")).toBe("full");
  await shot(page, "atlas-detailed", info);
  await setDetail(page, "Simple");
  await expect(page.getByTestId("full-evidence")).toHaveCount(0);
  const url = new URL(page.url());
  expect([url.searchParams.get("reference"), url.searchParams.get("site"), url.searchParams.get("view")]).toEqual(["mars-jezero", "earth-atacama-south", null]);
  await expect(page.getByTestId("result-earth-atacama-south")).toHaveAttribute("aria-current", "true");
});

test("blocked map tiles never leave a blank primary visual", async ({ page }, info) => {
  await page.route(GIBS, (route) => route.abort());
  await openAtlas(page, "/?site=earth-atacama-south");
  // The primary visual is the cached study-window image, served by the AlterEcho API, so it is unaffected.
  await plateLoaded(page);
  await expect(page.getByTestId("plate-caption")).toContainText("Sentinel-2 true colour · acquired");
  await page.getByTestId("site-viewer").scrollIntoViewIfNeeded();
  await page.getByRole("tab", { name: "Interactive map" }).click();
  await expect(page.getByTestId("site-explorer")).toBeVisible();
  const chip = page.getByTestId("tile-fallback");
  await expect(chip).toBeVisible({ timeout: 30_000 });
  await expect(chip).toContainText("study-window image shown");
  const box = await chip.boundingBox();
  expect(box!.height).toBeLessThan(60);
  await expect(page.locator(".explorer-overlay-note")).toHaveCount(0);
  await expect(page.getByTestId("explorer-caption")).toContainText("exact 10 km analysis boundary");
  // The study-window image is drawn on the map even with the background blocked.
  await expect(page.getByTestId("overlay-wait")).toHaveCount(0, { timeout: 30_000 });
  await expect(page.getByTestId("overlay-failed")).toHaveCount(0);
  await page.getByTestId("site-explorer").scrollIntoViewIfNeeded();
  await shot(page, "map-fallback", info);
  await page.getByTestId("tile-retry").click();
  // Still blocked, so the small notice returns; it never grows into a banner.
  await expect(chip).toBeVisible({ timeout: 30_000 });
});

test("the sticky header keeps one height and nothing scrolls over it", async ({ page }, info) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openAtlas(page);
  const expected = isMobile(page) ? 56 : 60;
  for (const y of [0, 500, 1200, 2400]) {
    await page.evaluate((top) => window.scrollTo(0, top), y);
    await page.waitForTimeout(150);
    const state = await page.evaluate(() => {
      const header = document.querySelector<HTMLElement>("[data-testid='masthead']")!;
      const r = header.getBoundingClientRect();
      const xs = [8, innerWidth / 2, innerWidth - 8];
      const covered = xs.map((x) => document.elementFromPoint(x, r.height - 4)).filter((el) => !el || !header.contains(el)).length;
      return { top: r.top, height: Math.round(r.height), covered };
    });
    expect(state).toEqual({ top: 0, height: expected, covered: 0 });
  }
  await shot(page, "scrolled-header", info);
  // Choosing a site on a narrow screen scrolls its name to just below the header, never under it.
  if (isMobile(page)) {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.getByTestId("result-earth-atacama-south").click();
    await expect(page.locator(".site-name")).toHaveText("Atacama Desert");
    await expect.poll(async () => (await page.locator(".site-name").boundingBox())!.y, { timeout: 5_000 }).toBeGreaterThanOrEqual(expected);
  }
});

test("light and dark themes both render the lockup and the result", async ({ page }, info) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openAtlas(page);
  for (const theme of ["dark", "light"] as const) {
    await openMenuIfCollapsed(page);
    await page.getByLabel("Color theme").selectOption(theme);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expect(page.locator(theme === "dark" ? ".brand-mark-dark" : ".brand-mark-light")).toBeVisible();
    await expect(page.locator(theme === "dark" ? ".brand-mark-light" : ".brand-mark-dark")).toBeHidden();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("verdict")).toBeVisible();
    await shot(page, `theme-${theme}`, info);
  }
});

test("mobile navigation folds into a menu that opens, closes and navigates", async ({ page }, info) => {
  test.skip(page.viewportSize()!.width >= 960, "menu is used below 960 px");
  await openAtlas(page);
  const button = page.getByTestId("menu-button");
  const nav = page.getByRole("navigation", { name: "Primary" });
  await expect(button).toBeVisible();
  await expect(nav.getByRole("link", { name: "Method", exact: true })).toBeHidden();
  await button.click();
  await expect(button).toHaveAttribute("aria-expanded", "true");
  await expect(nav.getByRole("link", { name: "Method", exact: true })).toBeVisible();
  await expect(page.getByTestId("detail-toggle")).toBeVisible();
  await shot(page, "mobile-menu", info);
  await page.keyboard.press("Escape");
  await expect(button).toHaveAttribute("aria-expanded", "false");
  await expect(button).toBeFocused();
  await button.click();
  await nav.getByRole("link", { name: "Method", exact: true }).click();
  await expect(page).toHaveURL(/\/method$/);
  await expect(button).toHaveAttribute("aria-expanded", "false");
});

test("URL state: direct links, back and forward restore reference, site and comparison", async ({ page }) => {
  await openAtlas(page, "/?reference=mars-gale-aeolis-palus&site=earth-meteor-crater&compare=temperature");
  await expect(page.getByTestId("reference-picker")).toContainText("Gale Crater floor");
  await expect(page.getByTestId("mode-temperature")).toHaveAttribute("aria-checked", "true");
  await expect(page.locator(".site-name")).toHaveText("Meteor Crater (Barringer)");

  await openAtlas(page, "/");
  await page.getByTestId("result-earth-atacama-south").click();
  await expect(page.locator(".site-name")).toHaveText("Atacama Desert");
  await page.getByTestId("result-earth-hanksville-mdrs").click();
  await expect(page.locator(".site-name")).toHaveText("Hanksville badlands (MDRS)");
  await page.getByTestId("mode-fieldwork").click();
  await expect(page.getByTestId("mode-fieldwork")).toHaveAttribute("aria-checked", "true");
  await page.goBack();
  await expect(page.getByTestId("mode-terrain")).toHaveAttribute("aria-checked", "true");
  await page.goBack();
  await expect(page.locator(".site-name")).toHaveText("Atacama Desert");
  await expect(page.getByTestId("result-earth-atacama-south")).toHaveAttribute("aria-current", "true");
  await page.goForward();
  await expect(page.locator(".site-name")).toHaveText("Hanksville badlands (MDRS)");
  await pickReference(page, "mars-gusev-plains");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Gusev");
  await page.goBack();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Jezero Crater");
  expect(new URL(page.url()).searchParams.get("site")).toBe("earth-hanksville-mdrs");
});

test("keyboard only: choose a reference, a comparison and a site", async ({ page }) => {
  await openAtlas(page);
  const picker = page.getByTestId("reference-picker");
  await picker.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("reference-mars-jezero")).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByTestId("reference-mars-gale-aeolis-palus")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(picker).toBeFocused();
  await expect(picker).toHaveAttribute("aria-expanded", "false");
  expect(new URL(page.url()).searchParams.get("reference")).toBe("mars-gale-aeolis-palus");

  await page.getByTestId("mode-terrain").focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByTestId("mode-temperature")).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("mode-temperature")).toBeFocused();
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByTestId("mode-terrain")).toHaveAttribute("aria-checked", "true");

  const row = page.getByTestId("result-earth-atacama-south");
  await row.focus();
  const outline = await row.evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(outline).not.toBe("none");
  await page.keyboard.press("Enter");
  await expect(row).toHaveAttribute("aria-current", "true");
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByText("Skip to content", { exact: true })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();
});

test("reduced motion turns entrance animations and crossfades off", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openAtlas(page);
  await plateLoaded(page);
  const card = await page.locator(".card-enter").evaluate((el) => getComputedStyle(el).animationName);
  const fade = await page.getByTestId("study-plate").getByRole("img").first().evaluate((el) => getComputedStyle(el).transitionDuration);
  expect(card).toBe("none");
  expect(fade).toBe("0s");
});

test("a failed context request is explained and can be retried", async ({ page }) => {
  await page.route("**/api/v3/context**", (route) => route.abort());
  await page.goto("/?compare=temperature");
  await expect(page.getByRole("alert").filter({ hasText: "could not be loaded" })).toBeVisible();
  await expect(page.getByTestId("context-note")).toContainText("Not part of the terrain result");
  await page.unroute("**/api/v3/context**");
  await page.getByRole("button", { name: "Try again" }).first().click();
  await expect(page.getByTestId("temperature-chart")).toBeVisible();
});
