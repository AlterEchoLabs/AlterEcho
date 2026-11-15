import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import type { EvidenceCompareResponse, CompareResponseV2 } from "../lib/evidence";
import type { CompareV3 } from "../lib/analogue";
import { openMenuIfCollapsed, pickReference, setDetail } from "./helpers";

const API = "http://127.0.0.1:8100";
// Third-party map tiles (NASA GIBS, OpenFreeMap) can be slow or blocked in CI; their network notices are not app errors.
const EXTERNAL = /gibs\.earthdata\.nasa\.gov|tiles\.openfreemap\.org/;

function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    if (/GPU stall|WebGL|swiftshader/i.test(message.text()) || EXTERNAL.test(message.location().url)) return;
    errors.push(message.text());
  });
  return errors;
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page must not scroll horizontally").toBeLessThanOrEqual(0);
}

async function expectHeadingsNotClipped(page: Page) {
  const clipped = await page.evaluate(() => [...document.querySelectorAll("h1, h2, h3")]
    .filter((el) => (el as HTMLElement).offsetParent !== null && el.scrollWidth > el.clientWidth + 1)
    .map((el) => el.textContent));
  expect(clipped).toEqual([]);
}

const selectSite = (page: Page, siteId: string) => page.getByTestId(`result-${siteId}`).click();

test.describe("atlas", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("results-list")).toBeVisible();
  });

  test("1 · terrain shape: top three in Simple, class groups on demand, standing among ordinary land, no rank badges", async ({ page }) => {
    const errors = watchErrors(page);
    await expect(page.getByRole("heading", { level: 1, name: "Jezero Crater" })).toBeVisible();
    await expect(page.getByTestId("reference-mars-jezero")).toHaveAttribute("aria-selected", "true");
    await page.getByTestId("reference-picker").click();
    await expect(page.getByTestId("reference-cards").getByRole("option")).toHaveCount(6);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("reference-cards")).toBeHidden();
    await expect(page.getByTestId("mode-terrain")).toHaveAttribute("aria-checked", "true");

    // Simple: the three closest sites, each "N/100" with how many of the 88 ordinary windows it beats; no "1 (tie)" or "6=" labels.
    await expect(page.getByTestId("results-list").getByRole("button")).toHaveCount(3);
    await expect(page.getByTestId("order-note")).toContainText("order is not meaningful");
    await expect(page.getByTestId("result-earth-atacama-south")).toContainText("Atacama Desert");
    await expect(page.getByTestId("result-earth-atacama-south")).toContainText("98/100");
    await expect(page.getByTestId("result-earth-atacama-south")).toContainText("beats 73 of 88 ordinary");
    await expect(page.getByTestId("results-list")).not.toContainText(/\(tie\)|\d=/);
    await expect(page.getByTestId("base-rate")).toContainText(/88 ordinary windows/);
    await expect(page.getByTestId("group-label")).toHaveCount(0);
    await page.getByTestId("show-all").click();
    const groups = page.getByTestId("group-label");
    await expect(groups).toHaveCount(2);
    await expect(groups.first()).toContainText("Same terrain class as Jezero Crater · 5");
    await expect(groups.nth(1)).toContainText("Different terrain from Jezero Crater · 2");
    await expect(page.getByTestId("results-list")).not.toContainText("first window");
    await expect(page.getByTestId("unmeasured-earth-holuhraun")).toContainText("outside SRTM elevation coverage");

    // Simple result: verdict, one index with its context, why it matched and the main limitation; no charts or tables.
    const simple = page.getByTestId("simple-result");
    await expect(page.getByTestId("verdict")).toContainText("Close terrain match");
    await expect(page.getByTestId("simple-index")).toContainText("Terrain similarity index");
    await expect(page.getByTestId("simple-index")).toContainText("Present-day terrain shape at a 60 m analysis grid");
    await expect(page.getByTestId("standing")).toContainText("of 88 ordinary Earth windows are less similar");
    await expect(page.getByTestId("why-short")).toContainText("of the typical difference between two ordinary Earth landscapes");
    await expect(page.getByTestId("main-limitation")).toContainText("terrain only");
    await expect(simple).toContainText("terrain only");
    await expect(page.getByTestId("simple-index")).not.toContainText("%");
    await expect(page.getByTestId("ordinary-chart")).toHaveCount(0);
    await expect(page.getByTestId("full-evidence")).toBeHidden();
    const plate = page.getByTestId("study-plate");
    await expect.poll(() => plate.getByRole("img").first().evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth)).toBe(1000);
    await expect(page.getByTestId("plate-caption")).toContainText("Sentinel-2 true colour · acquired");

    for (const id of ["earth-ladakh", "earth-meteor-crater", "earth-danakil", "earth-hanksville-mdrs", "earth-upper-mustang"]) await selectSite(page, id);
    await expect(page.getByTestId("result-earth-upper-mustang")).toHaveAttribute("aria-current", "true");
    await expect(page.getByTestId("site-viewer")).toHaveAttribute("data-site-id", "earth-upper-mustang");
    await expect(page.locator(".site-name")).toHaveText("Upper Mustang");
    await expect(page.getByTestId("verdict")).toContainText("Different terrain");
    await expect(page.getByTestId("why-short")).toContainText(/Slope differs by \d\.\d× and relief by \d\.\d× the typical difference/);
    expect(new URL(page.url()).searchParams.get("site")).toBe("earth-upper-mustang");
    await expectNoHorizontalOverflow(page);
    await expectHeadingsNotClipped(page);
    expect(errors).toEqual([]);
  });

  test("2 · compare by temperature and field tests: measured context, clearly not scored", async ({ page }) => {
    await selectSite(page, "earth-atacama-south");
    await page.getByTestId("mode-temperature").click();
    await expect(page.getByTestId("mode-hint")).toContainText("not scored");
    await expect(page.getByTestId("temperature-chart")).toBeVisible();
    await expect(page.getByTestId("simple-result")).toContainText("not scored");
    await expect(page.getByTestId("result-earth-atacama-south")).toContainText("°");
    await expect(page.getByTestId("site-sort")).toHaveCount(0);
    expect(new URL(page.url()).searchParams.get("compare")).toBe("temperature");
    await page.getByTestId("simple-result").getByText("Why temperature is not scored").click();
    await expect(page.getByTestId("simple-result")).toContainText("Spatial support");

    await page.getByTestId("mode-fieldwork").click();
    await expect(page.getByTestId("result-earth-hanksville-mdrs")).toContainText("studied here");
    await expect(page.getByTestId("result-earth-upper-mustang")).toContainText("no study found");
    await expect(page.getByTestId("simple-result")).toContainText("Studied in the region, not at this window");
    await expect(page.getByTestId("context-note")).toContainText("does not change the terrain results");

    await page.goto("/?site=earth-ladakh&compare=fieldwork");
    await expect(page.getByTestId("mode-fieldwork")).toHaveAttribute("aria-checked", "true");
    await expect(page.locator(".site-name")).toHaveText("Ladakh");
    await page.getByTestId("mode-terrain").click();
    await expect(page.getByTestId("simple-index")).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test("3 · full calculation: rendered formulas, sensitivity, JSON export, detailed mode and shareable state", async ({ page }) => {
    await selectSite(page, "earth-hanksville-mdrs");
    // "Show the full calculation" switches the whole page to Detailed and keeps the selection.
    const toggle = page.getByTestId("toggle-full");
    await toggle.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("detail-toggle").getByRole("radio", { name: "Detailed", includeHidden: true })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByTestId("result-earth-hanksville-mdrs")).toHaveAttribute("aria-current", "true");
    const full = page.getByTestId("full-evidence");
    await expect(page.getByTestId("calc-table")).toContainText("Slope distribution");
    await expect(page.getByTestId("calc-table")).toContainText("Relative elevation distribution");
    await expect(full.locator(".katex").first()).toBeVisible();
    await expect(full.locator(".katex-html").first()).toBeVisible();
    await expect(page.getByTestId("family-table")).toContainText("F1 Terrain morphology");
    await expect(page.getByTestId("sensitivity-table")).toContainText("Earth DEM");
    await expect(page.getByTestId("sensitivity-table")).not.toContainText("Rank");
    await expect(page.getByTestId("tolerance-table")).toBeVisible();
    await expect(full.getByRole("img", { name: /Slope distribution: quantile functions/ })).toBeVisible();
    expect(new URL(page.url()).searchParams.get("view")).toBe("full");

    const download = page.waitForEvent("download");
    await page.getByTestId("download-json").click();
    expect((await download).suggestedFilename()).toBe("alterecho-earth-hanksville-mdrs-mars-jezero.json");

    await page.reload();
    await expect(page.getByTestId("calc-table")).toBeVisible();
    await full.getByRole("button", { name: "Hide" }).first().click();
    await expect(page.getByTestId("full-evidence")).toBeHidden();
    expect(new URL(page.url()).searchParams.get("view")).toBeNull();

    // Detailed mode opens the calculation by default and is remembered.
    await setDetail(page, "Detailed");
    await expect(page.getByTestId("calc-table")).toBeVisible();
    await expect(page.getByTestId("toggle-full")).toHaveCount(0);
    await expect(page.getByTestId("score-range")).toContainText(/range \d+–\d+ across \d+ checks/);
    await page.reload();
    await expect(page.getByTestId("detail-toggle").getByRole("radio", { name: "Detailed", includeHidden: true })).toHaveAttribute("aria-checked", "true");
    await setDetail(page, "Simple");
    await expect(page.getByTestId("full-evidence")).toBeHidden();
    expect(new URL(page.url()).searchParams.get("site")).toBe("earth-hanksville-mdrs");
    await expectNoHorizontalOverflow(page);
  });

  test("4 · why this data explains every product and what it cannot establish", async ({ page }) => {
    await page.getByTestId("why-data").click();
    const dialog = page.getByTestId("why-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByTestId("role-srtmgl1")).toContainText("Scored input");
    await expect(dialog.getByTestId("role-srtmgl1")).toContainText("soil strength");
    await expect(dialog.getByTestId("role-sentinel2")).toContainText("Display only");
    await expect(dialog.getByTestId("role-sentinel2")).toContainText("geology or mineralogy");
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("5 · study window: still plate first, interactive globe below, zoom capped at the image's detail", async ({ page }) => {
    const errors = watchErrors(page);
    // Meteor Crater is fourth, so Simple keeps it behind "Show all"; a direct link opens it.
    await page.goto("/?site=earth-meteor-crater");
    await expect(page.getByTestId("result-earth-meteor-crater")).toHaveAttribute("aria-current", "true");
    // The plate shows the cached Sentinel-2 crop of the exact window; hillshade and slope come from the scoring DEM.
    const plate = page.getByTestId("study-plate");
    const image = plate.getByRole("img", { name: /Meteor Crater.*study area/ });
    await expect.poll(() => image.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth)).toBe(1000);
    await expect(page.getByTestId("plate-caption")).toContainText("Sentinel-2 true colour · acquired 12 Nov 2026");
    await setDetail(page, "Detailed");
    const legend = page.getByTestId("plate-legend");
    for (const text of ["Footprint coverage", "not clear sky", "AOI cloud", "Scene cloud"]) await expect(legend).toContainText(text);
    await page.getByTestId("plate-hillshade").click();
    await expect(plate).toHaveAttribute("data-layer", "hillshade");
    await expect(legend.getByText(/DEM SHA-256/)).toBeVisible();
    await setDetail(page, "Simple");

    // The viewer opens on the side-by-side comparison; the interactive globe is the last tab.
    await page.getByTestId("site-viewer").scrollIntoViewIfNeeded();
    await expect(page.getByRole("tab", { name: "Compare with reference" })).toHaveAttribute("aria-selected", "true");
    await page.getByRole("tab", { name: "Interactive map" }).click();
    const explorer = page.getByTestId("site-explorer");
    await explorer.scrollIntoViewIfNeeded();
    const caption = page.getByTestId("explorer-caption");
    await expect(caption).toContainText("source 10 m inside the window", { timeout: 30_000 });
    await expect(caption).toContainText(/Sentinel-2 L2A 2026-11-12/);
    await expect(caption).toContainText("exact 10 km analysis boundary");
    await expect(page.getByTestId("overlay-wait")).toHaveCount(0, { timeout: 30_000 });
    const zoomOf = async () => Number((await caption.innerText()).match(/Zoom (\d+(\.\d+)?)/)![1]);
    const before = await zoomOf();
    const zoomIn = explorer.getByRole("button", { name: "Zoom in" });
    // MapLibre disables the control once the cap is reached; a click on a disabled control is not an error here.
    for (let i = 0; i < 6; i++) { await zoomIn.click({ timeout: 1500 }).catch(() => undefined); await page.waitForTimeout(500); }
    // Either zoom increased, or the map is already at the cap and MapLibre disables the control.
    await expect.poll(async () => (await zoomOf()) > before || !(await zoomIn.isEnabled()), { timeout: 10_000 }).toBe(true);
    await expect.poll(zoomOf, { timeout: 10_000 }).toBeLessThanOrEqual(15);
    await explorer.getByRole("radio", { name: "Hillshade" }).click();
    await expect(caption).toContainText("Same SRTMGL1.003 DEM as the terrain measurement");
    await page.getByRole("button", { name: "Whole Earth" }).click();
    await expect(caption).toContainText("Global orientation mosaic", { timeout: 15_000 });
    await page.getByTestId("fit-aoi").click();
    await expect(caption).toContainText("inside the window", { timeout: 15_000 });

    await page.getByRole("tab", { name: "Interactive map" }).focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "Compare with reference" })).toHaveAttribute("aria-selected", "true");
    await page.getByRole("tab", { name: "3D terrain" }).click();
    await page.getByRole("checkbox", { name: /alongside/ }).check();
    await expect(page.getByText(/both surfaces share one vertical scale/)).toBeVisible();
    await expectNoHorizontalOverflow(page);
    expect(errors).toEqual([]);
  });

  test("6 · lunar reference, the not-scored Atacama window, unmeasured sites, missing imagery and an unreachable API are explained", async ({ page }) => {
    await pickReference(page, "moon-south-pole-shackleton");
    await expect(page.getByRole("heading", { level: 1, name: "Lunar south pole (Shackleton rim)" })).toBeVisible();
    await expect(page.getByTestId("reference-not-scorable")).toContainText("distances are shown without an index");
    await expect(page.getByTestId("ordering-note")).toContainText("No index for the Moon");
    await expect(page.getByTestId("simple-conclusion")).toContainText("no index is given");
    await expect(page.getByTestId("simple-index")).toHaveCount(0);
    await expect(page.getByTestId("base-rate")).toHaveCount(0);
    expect(new URL(page.url()).searchParams.get("reference")).toBe("moon-south-pole-shackleton");

    // The first Atacama window is reachable by link and explains why it is not scored.
    await page.goto("/?site=earth-atacama");
    await expect(page.getByTestId("simple-result")).toContainText("industrial complex");
    await page.getByTestId("unmeasured-earth-holuhraun").click();
    await expect(page.getByTestId("site-viewer")).toHaveAttribute("data-site-id", "earth-holuhraun");
    await expect(page.getByTestId("simple-result")).toContainText("outside SRTM elevation coverage");
    await expect(page.getByRole("tab", { name: "Globe (orientation)" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Interactive map" })).toHaveCount(0);

    // No processed satellite crop: the plate shows the DEM hillshade of the same window and says so.
    await page.route(`${API}/api/v3/sites/earth-ladakh/explorer`, async (route) => {
      const response = await route.fetch();
      await route.fulfill({ response, json: { ...(await response.json()), imagery: null } });
    });
    await page.goto("/?site=earth-ladakh");
    await expect(page.getByTestId("study-plate")).toHaveAttribute("data-layer", "hillshade");
    await expect(page.getByTestId("plate-caption")).toContainText("No satellite crop has been processed for this site");
    await expect(page.getByTestId("plate-satellite")).toBeDisabled();

    // The crop exists but fails to load: same fallback, with the reason.
    await page.route(`${API}/api/imagery-assets/**`, (route) => route.abort());
    await page.goto("/?site=earth-hanksville-mdrs");
    await expect(page.getByTestId("study-plate")).toHaveAttribute("data-layer", "hillshade");
    await expect(page.getByTestId("plate-caption")).toContainText("The satellite image could not be loaded");

    await page.route(`${API}/api/**`, (route) => route.abort());
    await page.goto("/");
    await expect(page.getByRole("alert").filter({ hasText: /not reachable|could not be loaded/ }).first()).toBeVisible();
  });

  test("6b · switching the Mars reference changes values, images, compare view, links and exports", async ({ page }) => {
    const errors = watchErrors(page);
    const jezeroText = await page.getByTestId("result-earth-craters-of-the-moon").innerText();
    await pickReference(page, "mars-gale-aeolis-palus");
    await expect(page.getByRole("heading", { level: 1, name: "Gale Crater floor (Aeolis Palus)" })).toBeVisible();
    await expect(page.getByTestId("standing")).toContainText("less similar to Gale Crater floor");
    await expect(page.locator(".site-meta")).toContainText("compared with Gale");
    await expect.poll(() => page.getByTestId("result-earth-craters-of-the-moon").innerText()).not.toBe(jezeroText);
    expect(new URL(page.url()).searchParams.get("reference")).toBe("mars-gale-aeolis-palus");
    await page.getByText("About this reference window").click();
    await expect(page.locator(".ref-about-body")).toContainText("Curiosity");
    await expect(page.locator(".ref-about-body")).toContainText("DOI 10.5066/P9JKVWR3");

    await page.getByTestId("site-viewer").scrollIntoViewIfNeeded();
    await page.getByRole("tab", { name: "Compare with reference" }).click();
    const compare = page.getByTestId("synced-compare");
    await expect(compare.getByRole("img", { name: /CTX orthoimage.*Gale Crater floor/ })).toBeVisible();
    await expect.poll(() => compare.getByRole("img", { name: /CTX orthoimage/ }).evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth)).toBe(1000);
    await compare.getByRole("button", { name: "Zoom both views in" }).click();
    await expect(page.getByTestId("synced-caption")).toContainText("zoom 1.25×");
    await compare.scrollIntoViewIfNeeded();
    const scrollBeforeWheel = await page.evaluate(() => window.scrollY);
    const compareBox = await compare.boundingBox();
    if (!compareBox) throw new Error("comparison view has no layout box");
    await page.mouse.move(compareBox.x + compareBox.width / 2, compareBox.y + compareBox.height / 2);
    await page.mouse.wheel(0, 600);
    expect(await page.evaluate(() => window.scrollY)).toBe(scrollBeforeWheel);
    await compare.getByRole("radio", { name: "Hillshade" }).click();
    await expect(compare.getByRole("img", { name: /hillshade of the 10 km Gale Crater floor/ })).toBeVisible();

    // Report and JSON export are provenance, so they live in Detailed.
    await expect(page.getByTestId("download-json")).toHaveCount(0);
    await setDetail(page, "Detailed");
    await expect(page.getByRole("link", { name: "Printable report" })).toHaveAttribute("href", /reference=mars-gale-aeolis-palus/);
    const download = page.waitForEvent("download");
    await page.getByTestId("download-json").click();
    expect((await download).suggestedFilename()).toContain("mars-gale-aeolis-palus");
    await expectNoHorizontalOverflow(page);
    expect(errors).toEqual([]);
  });

  test("6c · candidate search and ordering (Detailed)", async ({ page }) => {
    await expect(page.getByTestId("site-search")).toHaveCount(0);
    await setDetail(page, "Detailed");
    await page.getByTestId("site-search").fill("meteor");
    await expect(page.getByTestId("results-list").getByRole("button")).toHaveCount(1);
    await expect(page.getByTestId("result-earth-meteor-crater")).toBeVisible();
    await page.getByTestId("site-search").fill("");
    await page.getByTestId("site-sort").selectOption("name");
    await expect(page.getByTestId("group-label")).toHaveCount(0);
    await expect(page.getByTestId("results-list").getByRole("button").first()).toContainText("Atacama Desert");
    await page.getByTestId("site-sort").selectOption("closeness");
    await expect(page.getByTestId("group-label")).toHaveCount(2);
  });

  test("7 · printable report reproduces the full evidence for one comparison", async ({ page }) => {
    await page.goto("/report?site=earth-craters-of-the-moon&profile=terrain_analogy&reference=mars-jezero");
    await expect(page.getByRole("heading", { level: 1, name: "Craters of the Moon lava field compared with Jezero Crater" })).toBeVisible();
    for (const h of ["Result", "Full evidence and calculations"]) await expect(page.getByRole("heading", { level: 2, name: h })).toBeVisible();
    await expect(page.getByTestId("calc-table")).toBeVisible();
    await expect(page.getByTestId("report")).toContainText("is not resolved from the Jezero Crater window by these tests");
    await expect(page.getByTestId("report-standing")).toContainText("of 88");
    await expectNoHorizontalOverflow(page);
  });
});

// ---- Explore: job states are mocked so ordinary runs make no Earthdata or Planetary Computer calls ----

const JOB_ID = "0123456789abcdef0123456789abcdef";
const SQUARE = { type: "Polygon", coordinates: [[[-116.82, 36.18], [-116.71, 36.18], [-116.71, 36.27], [-116.82, 36.27], [-116.82, 36.18]]] };
const PREFLIGHT = {
  center: { lat: 36.2297, lon: -116.7669 }, geometry: SQUARE, width_m: 10000, supported: true, reason: null,
  processing: { available: true, reason: null },
  dem: { product: "SRTMGL1 v003", native_resolution: "1 arc-second (~30 m)", analysis_scales_m: [60, 120, 240], tiles: ["N36W117"], tiles_cached: [], credentials_available: true, requires_credentials: false },
  imagery: { product: "Sentinel-2 L2A", authentication: "anonymous SAS", note: "mocked for the test" }, references: ["mars-jezero", "moon-south-pole-shackleton"],
  queue: { pending: 0, max: 4 }, limits: { per_client_per_hour: 3, global_per_day: 40 },
};
const feats = { slope: { label: "Slope distribution", units: "degrees", distance: 2.1, tau: 5.81, similarity: 0.91, role: "scored" }, relative_elevation: { label: "Relative elevation distribution", units: "metres", distance: 30, tau: 77.1, similarity: 0.9, role: "scored" } };
const RESULT = {
  label: "screening", method_version: "analogue-method-v1.0", inputs: [{ tile_id: "N36W117", file: "N36W117.SRTMGL1.hgt.zip", sha256: "f".repeat(64), product: "SRTMGL1" }], coverage: {}, metrics_60m: {},
  comparisons: {
    "mars-jezero": { reference_name: "Jezero Crater", method: "analogue-method-v1.0", scored: true, terrain_index: 55.0, terrain_class: "same", standing: { closer_than: 30, as_close_or_closer: 58, of: 88, statement: "Closer to Jezero Crater than 30 of 88 ordinary Earth land windows" }, reason: null, features: feats },
    "moon-south-pole-shackleton": { reference_name: "Lunar south pole (Shackleton rim)", method: "analogue-method-v1.0", scored: false, terrain_index: null, terrain_class: null, standing: null, reason: "floor", features: feats },
  },
  imagery: { status: "unavailable", reason: "mocked: imagery is not requested in tests" }, limitations: ["Mocked result used only to exercise the interface."], result_sha256: "e".repeat(64),
};

function job(state: string, extra: Record<string, unknown> = {}) {
  return { job_id: JOB_ID, label: "Death Valley (mocked)", state, center: PREFLIGHT.center, geometry: SQUARE, created_at: "2026-11-14T00:00:00Z", updated_at: "2026-11-14T00:00:00Z",
    log: [{ at: "2026-11-14T00:00:00Z", state, message: `${state} step (mocked)` }], preflight: PREFLIGHT, screening: true, result: null, ...extra };
}

async function mockExplore(page: Page, sequence: Record<string, unknown>[]) {
  await page.route(`${API}/api/explore/preflight`, (route) => route.fulfill({ json: PREFLIGHT }));
  await page.route(`${API}/api/explore/jobs`, (route) => route.request().method() === "POST" ? route.fulfill({ status: 202, json: sequence[0] }) : route.fulfill({ json: [] }));
  let call = 0;
  await page.route(`${API}/api/explore/jobs/${JOB_ID}`, (route) => route.fulfill({ json: sequence[Math.min(call++, sequence.length - 1)] }));
}

async function chooseDeathValley(page: Page) {
  await page.goto("/explore");
  await page.getByLabel("Latitude in decimal degrees").fill("36.2297");
  await page.getByLabel("Longitude in decimal degrees").fill("-116.7669");
  await page.getByRole("button", { name: "Set" }).click();
  await expect(page.getByTestId("preflight")).toContainText("SRTMGL1 v003");
}

test("8 · explore: a screening job moves through every state and shows a labelled screening result", async ({ page }) => {
  await mockExplore(page, [job("queued"), job("acquiring"), job("processing"), job("quality_check"), job("ready", { result: RESULT })]);
  await chooseDeathValley(page);
  await page.getByTestId("submit-screening").click();
  await expect(page.getByTestId("job-panel")).toBeVisible();
  await expect(page.getByTestId("job-result")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("job-result")).toContainText("screening · not reviewed");
  await expect(page.getByTestId("job-result")).toContainText("55/100");
  await expect(page.getByTestId("job-result")).toContainText("30 of 88");
  await expect(page.getByTestId("screening-table")).toContainText("no index");
  await expect(page.locator(".job-steps li.done")).toHaveCount(5);
  expect(new URL(page.url()).searchParams.get("job")).toBe(JOB_ID);
  await expectNoHorizontalOverflow(page);
});

test("9 · explore: missing credentials, unsupported areas and provider failures are shown as states", async ({ page }) => {
  await mockExplore(page, [job("requires_credentials")]);
  await chooseDeathValley(page);
  await page.getByTestId("submit-screening").click();
  await expect(page.getByTestId("job-panel").getByRole("alert")).toContainText("requires credentials");
  await expect(page.getByTestId("job-result")).toHaveCount(0);

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockExplore(page, [job("acquiring"), job("failed")]);
  await chooseDeathValley(page);
  await page.getByTestId("submit-screening").click();
  await expect(page.getByTestId("job-panel").getByRole("alert")).toContainText("failed", { timeout: 15_000 });

  // Real backend: Haughton Crater lies outside SRTM coverage, so no job can be submitted.
  await page.unrouteAll({ behavior: "ignoreErrors" });
  await page.goto("/explore");
  await page.getByLabel("Documented analog places").selectOption({ label: "Haughton Crater, Devon Island (outside SRTM)" });
  await expect(page.getByTestId("preflight")).toContainText(/outside|coverage/i);
  await expect(page.getByTestId("submit-screening")).toBeDisabled();

  // A serverless deployment must explain its native-worker limitation instead of looking unreachable.
  await page.unrouteAll({ behavior: "ignoreErrors" });
  await page.route(`${API}/api/explore/preflight`, (route) => route.fulfill({
    json: { ...PREFLIGHT, processing: { available: false, reason: "Custom-area processing requires Rasterio/GDAL and a persistent worker." } },
  }));
  await chooseDeathValley(page);
  await expect(page.getByTestId("preflight")).toContainText("requires Rasterio/GDAL and a persistent worker");
  await expect(page.getByTestId("submit-screening")).toBeDisabled();
});

test("10 · method and sources pages load with live data", async ({ page }) => {
  await page.goto("/");
  // Wait for hydration (the results list only renders after the client fetch); a Link clicked before that can be dropped.
  await expect(page.getByTestId("results-list")).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Primary" });
  await openMenuIfCollapsed(page);
  await nav.getByRole("link", { name: "Method", exact: true }).click();
  await expect(page).toHaveURL(/\/method$/);
  await expect(page.getByRole("heading", { level: 1, name: "How every number is made" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Worked example from stored data" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Temperature comparability audit" })).toBeVisible();
  await expect(page.getByTestId("decomposition")).toContainText("Craters of the Moon lava field");
  await expect(page.getByTestId("method-references")).toContainText("Gale Crater floor (Aeolis Palus)");
  await expect(page.getByTestId("method-references")).toContainText("distances only");
  await expect(page.getByTestId("method-discrimination")).toContainText("Eberswalde crater delta");
  await expect(page.getByTestId("worked-example")).toContainText("Shown in the atlas as");
  await expect(page.locator(".method-page .katex").first()).toBeVisible();
  await expect(page.locator(".method-page .katex-html").first()).toBeVisible();
  await expect(page.getByTestId("thermal-audit")).toContainText(/Spatial support/);
  await expectNoHorizontalOverflow(page);
  await openMenuIfCollapsed(page);
  await nav.getByRole("link", { name: "Data & sources", exact: true }).click();
  await expect(page).toHaveURL(/\/sources$/);
  await expect(page.getByRole("heading", { level: 1, name: "Data and sources" })).toBeVisible();
  await expect(page.getByTestId("registry")).toContainText("SRTMGL1");
  await expect(page.getByTestId("registry")).toContainText(/evaluated for later use/i);
  await expect(page.getByRole("heading", { level: 2, name: "Why each dataset is used" })).toBeVisible();
  await expect(page.getByTestId("data-roles")).toContainText("ESA WorldCover");
  await expectNoHorizontalOverflow(page);
});

const keys = (value: unknown): string[] => value && typeof value === "object" && !Array.isArray(value) ? Object.keys(value).sort() : [];

test("API contract: v2 comparison matches the typed frontend fixture", async ({ request }) => {
  const response = await request.post(`${API}/api/v2/compare`, { data: { profile_id: "terrain_analogy", reference_site_id: "mars-jezero" } });
  expect(response.ok()).toBeTruthy();
  const payload = (await response.json()) as CompareResponseV2;
  const fixture = JSON.parse(readFileSync(path.join(__dirname, "fixtures", "evidence-compare-v2.json"), "utf-8")) as CompareResponseV2;
  expect(keys(payload)).toEqual(keys(fixture));
  expect(keys(payload.results[0])).toEqual(keys(fixture.results[0]));
  expect(keys(payload.results[0].dimensions[0])).toEqual(keys(fixture.results[0].dimensions[0]));
  expect(payload.results.map((r) => [r.site_id, r.partial_index, r.rank])).toEqual(fixture.results.map((r) => [r.site_id, r.partial_index, r.rank]));
  expect(payload.tie_groups).toEqual(fixture.tie_groups);
});

test("API contract: analogue-method-v1.0 comparison matches the typed frontend fixture", async ({ request }) => {
  const response = await request.get(`${API}/api/v3/compare?reference=mars-jezero&profile=terrain_analogy`);
  expect(response.ok()).toBeTruthy();
  const payload = (await response.json()) as CompareV3;
  const fixture = JSON.parse(readFileSync(path.join(__dirname, "fixtures", "analogue-compare-v3.json"), "utf-8")) as CompareV3;
  expect(keys(payload)).toEqual(keys(fixture));
  expect(keys(payload.results[0])).toEqual(keys(fixture.results[0]));
  expect(keys(payload.results[0].families[0].features[0])).toEqual(keys(fixture.results[0].families[0].features[0]));
  expect(payload.results.map((r) => [r.site_id, r.state, r.observed_index, r.standing?.closer_than ?? null])).toEqual(fixture.results.map((r) => [r.site_id, r.state, r.observed_index, r.standing?.closer_than ?? null]));
  expect(payload.tie_groups).toEqual(fixture.tie_groups);
});

test("API contract: historical analog-evidence-v1 endpoint is preserved", async ({ request }) => {
  const response = await request.post(`${API}/api/evidence/compare`, { data: { candidate_site_ids: ["earth-atacama", "earth-upper-mustang", "earth-ladakh"], profile_id: "balanced_science" } });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  const fixture = JSON.parse(readFileSync(path.join(__dirname, "fixtures", "evidence-compare.json"), "utf-8")) as EvidenceCompareResponse;
  expect(keys(payload)).toEqual(keys(fixture));
  expect(payload.results.map((r: { index: number }) => r.index)).toEqual(fixture.results.map((r) => r.index));
});
