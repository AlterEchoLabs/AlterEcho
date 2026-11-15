import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import type { EvidenceCompareResponse, CompareResponseV2 } from "../lib/evidence";
import type { CompareV3 } from "../lib/analogue";

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

  test("1 · terrain analogy: tie groups, resolution floor, base rate, exclusion and a simple result by default", async ({ page }) => {
    const errors = watchErrors(page);
    await expect(page.getByRole("heading", { level: 1, name: "Jezero Crater" })).toBeVisible();
    await expect(page.getByTestId("profile-state")).toHaveText("Ranked on terrain");
    for (const id of ["earth-craters-of-the-moon", "earth-atacama-south", "earth-hanksville-mdrs", "earth-meteor-crater", "earth-danakil"]) {
      await expect(page.getByTestId(`result-${id}`).locator(".result-rank")).toHaveText("1 (tie)");
    }
    for (const id of ["earth-upper-mustang", "earth-ladakh"]) await expect(page.getByTestId(`result-${id}`).locator(".result-rank")).toHaveText("6 (tie)");
    await expect(page.getByTestId("tie-label").first()).toContainText("Tie group · 5 sites · order not resolved by the data");
    await expect(page.getByTestId("result-earth-craters-of-the-moon")).toContainText("Not resolved from the reference by the floor tests");
    await expect(page.getByTestId("result-earth-craters-of-the-moon")).toContainText(/top \d+% of background/);
    await expect(page.getByTestId("reference-mars-jezero")).toHaveAttribute("aria-checked", "true");
    await expect(page.getByTestId("reference-cards").getByRole("radio")).toHaveCount(5);
    await expect(page.getByTestId("base-rate")).toContainText(/of \d+ unselected Earth windows also score 90 or more/);
    await expect(page.getByTestId("excluded-earth-atacama")).toContainText("contaminated window");
    await expect(page.getByTestId("unmeasured-earth-holuhraun")).toBeVisible();

    // Simple result is the default and keeps scope and coverage visible.
    const simple = page.getByTestId("simple-result");
    await expect(simple).toContainText("terrain only");
    await expect(simple).toContainText("100% of the planned Terrain analogy evidence is measured and comparable");
    await expect(page.getByTestId("simple-index")).toContainText("Experimental terrain evidence index");
    await expect(page.getByTestId("background-text")).toContainText(/unselected Earth land windows score at least as high/);
    await expect(page.getByTestId("full-evidence")).toBeHidden();
    await expect(page.getByTestId("toggle-full")).toHaveAttribute("aria-expanded", "false");

    for (const id of ["earth-ladakh", "earth-meteor-crater", "earth-danakil", "earth-hanksville-mdrs", "earth-upper-mustang"]) await selectSite(page, id);
    await expect(page.getByTestId("result-earth-upper-mustang")).toHaveAttribute("aria-current", "true");
    await expect(page.getByTestId("site-viewer")).toHaveAttribute("data-site-id", "earth-upper-mustang");
    await expect(page.locator(".site-name")).toHaveText("Upper Mustang");
    await expect(page.getByTestId("simple-conclusion")).toContainText("differs from the Jezero Crater window by more than a typical pair of Earth land windows");
    expect(new URL(page.url()).searchParams.get("site")).toBe("earth-upper-mustang");
    await expectNoHorizontalOverflow(page);
    await expectHeadingsNotClipped(page);
    expect(errors).toEqual([]);
  });

  test("2 · partial and unassessable modes answer their own question and are never ranked", async ({ page }) => {
    await page.getByTestId("profile-balanced_science").click();
    await expect(page.getByTestId("profile-state")).toHaveText("Partial evidence · not ranked");
    await expect(page.getByTestId("profile-headline")).toContainText("30% of planned balanced science evidence measured");
    await expect(page.getByTestId("result-earth-atacama-south").locator(".result-rank")).toHaveText("·");
    await expect(page.getByTestId("simple-conclusion")).toContainText("Terrain evidence available; 30% of planned science evidence measured.");
    await expect(page.getByTestId("simple-index")).toHaveCount(0);
    await expect(page.getByTestId("base-rate")).toHaveCount(0);

    await page.getByTestId("profile-rover_mobility").click();
    await expect(page.getByTestId("simple-conclusion")).toContainText("Wheel-scale traversability, rock hazards and soil bearing strength have not been observed");
    await page.getByTestId("profile-biosignature_fieldwork").click();
    await expect(page.getByTestId("profile-state")).toHaveText("Not assessed");
    await expect(page.getByTestId("simple-conclusion")).toContainText("No claim is made that life has been observed on Mars");
    await page.getByTestId("profile-mars_base_field_testing").click();
    await expect(page.getByTestId("simple-conclusion")).toContainText("not base or landing-site suitability");
    expect(new URL(page.url()).searchParams.get("profile")).toBe("mars_base_field_testing");

    await page.goto("/?site=earth-ladakh&profile=balanced_science");
    await expect(page.getByTestId("profile-balanced_science")).toHaveAttribute("aria-checked", "true");
    await expect(page.locator(".site-name")).toHaveText("Ladakh");
  });

  test("3 · full evidence: calculations, formulas, sensitivity, JSON export and shareable state", async ({ page }) => {
    await selectSite(page, "earth-hanksville-mdrs");
    const toggle = page.getByTestId("toggle-full");
    await toggle.focus();
    await page.keyboard.press("Enter");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    const full = page.getByTestId("full-evidence");
    await expect(page.getByTestId("calc-table")).toContainText("Slope distribution");
    await expect(page.getByTestId("calc-table")).toContainText("Relative elevation distribution");
    await expect(full).toContainText("s_k = exp(-ln 2 * (d_k / tau_k)^2)");
    await expect(page.getByTestId("family-table")).toContainText("F1 Terrain morphology");
    await expect(page.getByTestId("sensitivity-table")).toContainText("Earth DEM");
    await expect(page.getByTestId("tolerance-table")).toBeVisible();
    await expect(full.getByRole("img", { name: /Slope distribution: quantile functions/ })).toBeVisible();
    expect(new URL(page.url()).searchParams.get("view")).toBe("full");

    const download = page.waitForEvent("download");
    await page.getByTestId("download-json").click();
    expect((await download).suggestedFilename()).toBe("alterecho-earth-hanksville-mdrs-terrain_analogy-mars-jezero.json");

    await page.reload();
    await expect(page.getByTestId("calc-table")).toBeVisible();
    await full.getByRole("button", { name: "Back to simple result" }).first().click();
    await expect(page.getByTestId("full-evidence")).toBeHidden();
    expect(new URL(page.url()).searchParams.get("view")).toBeNull();
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

  test("5 · explorer: the globe flies to the exact 10 km window and caps zoom at the image's detail", async ({ page }) => {
    const errors = watchErrors(page);
    await selectSite(page, "earth-meteor-crater");
    const explorer = page.getByTestId("site-explorer");
    await explorer.scrollIntoViewIfNeeded();
    const caption = page.getByTestId("explorer-caption");
    await expect(caption).toContainText("source 10 m inside the window", { timeout: 30_000 });
    await expect(caption).toContainText(/Sentinel-2 L2A 2026-11-12/);
    await expect(caption).toContainText("exact 10 km analysis boundary");
    const zoomOf = async () => Number((await caption.innerText()).match(/Zoom (\d+(\.\d+)?)/)![1]);
    const before = await zoomOf();
    const zoomIn = explorer.getByRole("button", { name: "Zoom in" });
    // MapLibre disables the control once the cap is reached; a click on a disabled control is not an error here.
    for (let i = 0; i < 6; i++) { await zoomIn.click({ timeout: 1500 }).catch(() => undefined); await page.waitForTimeout(500); }
    // Either zoom increased, or the map is already at the cap and MapLibre disables the control.
    await expect.poll(async () => (await zoomOf()) > before || !(await zoomIn.isEnabled()), { timeout: 10_000 }).toBe(true);
    await expect.poll(zoomOf, { timeout: 10_000 }).toBeLessThanOrEqual(15);
    await page.getByRole("radio", { name: "Hillshade" }).click();
    await expect(caption).toContainText("Same SRTMGL1.003 DEM as the terrain measurement");
    await page.getByRole("button", { name: "Whole Earth" }).click();
    await expect(caption).toContainText("Global orientation mosaic", { timeout: 15_000 });
    await page.getByTestId("fit-aoi").click();
    await expect(caption).toContainText("inside the window", { timeout: 15_000 });

    await page.getByRole("tab", { name: "Image + details" }).click();
    const image = page.getByRole("img", { name: /Meteor Crater.*study area/ });
    await expect.poll(() => image.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth)).toBe(1000);
    const legend = page.locator(".plate-legend");
    for (const text of ["Footprint coverage", "not clear sky", "AOI cloud", "Scene cloud"]) await expect(legend).toContainText(text);
    await page.getByRole("tab", { name: "Image + details" }).focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "Elevation" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText(/DEM SHA-256/)).toBeVisible();
    await page.getByRole("tab", { name: "3D terrain" }).click();
    await page.getByRole("checkbox", { name: /alongside/ }).check();
    await expect(page.getByText(/both surfaces share one vertical scale/)).toBeVisible();
    await expectNoHorizontalOverflow(page);
    expect(errors).toEqual([]);
  });

  test("6 · lunar reference, excluded and unmeasured sites, missing imagery and an unreachable API are explained", async ({ page }) => {
    await page.getByRole("radio", { name: "Moon · 1", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Lunar south pole (Shackleton rim)" })).toBeVisible();
    await expect(page.getByTestId("reference-not-scorable")).toContainText("distances are shown without an index");
    await expect(page.getByTestId("profile-state")).toHaveText("Not assessed");
    await expect(page.getByTestId("simple-conclusion")).toContainText("no index is given");
    await expect(page.getByTestId("base-rate")).toHaveCount(0);
    expect(new URL(page.url()).searchParams.get("reference")).toBe("moon-south-pole-shackleton");

    await page.getByTestId("excluded-earth-atacama").click();
    await expect(page.getByTestId("simple-result")).toContainText("industrial complex");
    await page.getByTestId("unmeasured-earth-holuhraun").click();
    await expect(page.getByTestId("site-viewer")).toHaveAttribute("data-site-id", "earth-holuhraun");
    await expect(page.getByRole("tab", { name: "Globe (orientation)" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Explore map" })).toHaveCount(0);

    await page.route(`${API}/api/sites/earth-ladakh/imagery`, async (route) => {
      const response = await route.fetch();
      const records = (await response.json()) as { mode: string }[];
      await route.fulfill({ response, json: records.filter((r) => r.mode !== "reference") });
    });
    await page.goto("/?site=earth-ladakh");
    await page.getByRole("tab", { name: "Image + details" }).click();
    await expect(page.getByText(/No detailed crop has been processed for this site/)).toBeVisible();

    await page.route(`${API}/api/**`, (route) => route.abort());
    await page.goto("/");
    await expect(page.getByRole("alert").filter({ hasText: /not reachable|could not be loaded/ }).first()).toBeVisible();
  });

  test("6b · switching the Mars reference changes values, images, compare view, links and exports", async ({ page }) => {
    const errors = watchErrors(page);
    const jezeroText = await page.getByTestId("result-earth-craters-of-the-moon").innerText();
    await page.getByTestId("reference-mars-gale-aeolis-palus").click();
    await expect(page.getByRole("heading", { level: 1, name: "Gale Crater floor (Aeolis Palus)" })).toBeVisible();
    await expect(page.getByTestId("simple-result")).toContainText("Gale Crater floor (Aeolis Palus)");
    await expect.poll(() => page.getByTestId("result-earth-craters-of-the-moon").innerText()).not.toBe(jezeroText);
    expect(new URL(page.url()).searchParams.get("reference")).toBe("mars-gale-aeolis-palus");
    await page.getByText("About this reference window").click();
    await expect(page.locator(".ref-about-body")).toContainText("Curiosity");
    await expect(page.locator(".ref-about-body")).toContainText("DOI 10.5066/P9JKVWR3");

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

    await expect(page.getByRole("link", { name: "Printable report" })).toHaveAttribute("href", /reference=mars-gale-aeolis-palus/);
    const download = page.waitForEvent("download");
    await page.getByTestId("download-json").click();
    expect((await download).suggestedFilename()).toContain("mars-gale-aeolis-palus");
    await expectNoHorizontalOverflow(page);
    expect(errors).toEqual([]);
  });

  test("6c · candidate search and ordering stay within comparable results", async ({ page }) => {
    await page.getByTestId("site-search").fill("meteor");
    await expect(page.getByTestId("results-list").getByRole("button")).toHaveCount(1);
    await expect(page.getByTestId("result-earth-meteor-crater")).toBeVisible();
    await page.getByTestId("site-search").fill("");
    await page.getByTestId("site-sort").selectOption("name");
    await expect(page.getByTestId("tie-label")).toHaveCount(0);
    await page.getByTestId("site-filter").selectOption("rugged");
    await expect(page.getByTestId("result-earth-ladakh")).toBeVisible();
    await expect(page.getByTestId("result-earth-hanksville-mdrs")).toHaveCount(0);
    await page.getByTestId("profile-balanced_science").click();
    await expect(page.getByTestId("site-sort")).toHaveCount(0);
    await expect(page.locator(".list-tools")).toContainText("listed by name, never ranked");
  });

  test("7 · printable report reproduces the full evidence for one comparison", async ({ page }) => {
    await page.goto("/report?site=earth-craters-of-the-moon&profile=terrain_analogy&reference=mars-jezero");
    await expect(page.getByRole("heading", { level: 1, name: "Craters of the Moon lava field compared with Jezero Crater" })).toBeVisible();
    for (const h of ["Result", "Full evidence and calculations"]) await expect(page.getByRole("heading", { level: 2, name: h })).toBeVisible();
    await expect(page.getByTestId("calc-table")).toBeVisible();
    await expect(page.getByTestId("report")).toContainText("is not resolved from the Jezero Crater window by these tests");
    await expectNoHorizontalOverflow(page);
  });
});

// ---- Explore: job states are mocked so ordinary runs make no Earthdata or Planetary Computer calls ----

const JOB_ID = "0123456789abcdef0123456789abcdef";
const SQUARE = { type: "Polygon", coordinates: [[[-116.82, 36.18], [-116.71, 36.18], [-116.71, 36.27], [-116.82, 36.27], [-116.82, 36.18]]] };
const PREFLIGHT = {
  center: { lat: 36.2297, lon: -116.7669 }, geometry: SQUARE, width_m: 10000, supported: true, reason: null,
  dem: { product: "SRTMGL1 v003", native_resolution: "1 arc-second (~30 m)", analysis_scales_m: [60, 120, 240], tiles: ["N36W117"], tiles_cached: [], credentials_available: true, requires_credentials: false },
  imagery: { product: "Sentinel-2 L2A", authentication: "anonymous SAS", note: "mocked for the test" }, references: ["mars-jezero", "moon-south-pole-shackleton"],
  queue: { pending: 0, max: 4 }, limits: { per_client_per_hour: 3, global_per_day: 40 },
};
const families = { slope: { index: 70, w1_60m: 2.1, units: "degrees", tau: 3.4 }, local_relief: { index: 60, w1_60m: 20, units: "metres", tau: 25 }, roughness: { index: 50, w1_60m: 3, units: "metres", tau: 2.6 }, relative_elevation: { index: 40, w1_60m: 30, units: "metres", tau: 22 } };
const RESULT = {
  label: "screening", inputs: [{ tile_id: "N36W117", file: "N36W117.SRTMGL1.hgt.zip", sha256: "f".repeat(64), product: "SRTMGL1" }], coverage: {}, metrics_60m: {},
  base_rate: { share_at_or_above: { "99": 0.44 }, windows: 90 },
  comparisons: { "mars-jezero": { terrain_index: 55.0, method: "terrain-v4.0", families }, "moon-south-pole-shackleton": { terrain_index: 50.0, method: "terrain-v4.0", families } },
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
  await expect(page.getByTestId("job-result")).toContainText("55.0");
  await expect(page.getByTestId("job-result")).toContainText("limited lunar comparison");
  await expect(page.getByTestId("job-result")).toContainText("44%");
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
});

test("10 · method and sources pages load with live data", async ({ page }) => {
  await page.goto("/");
  // Wait for hydration (the results list only renders after the client fetch); a Link clicked before that can be dropped.
  await expect(page.getByTestId("results-list")).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Primary" });
  await nav.getByRole("link", { name: "Method", exact: true }).click();
  await expect(page).toHaveURL(/\/method$/);
  await expect(page.getByRole("heading", { level: 1, name: "How every number is made" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Worked example from stored data" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Temperature comparability audit" })).toBeVisible();
  await expect(page.getByTestId("decomposition")).toContainText("Craters of the Moon lava field");
  await expect(page.getByTestId("method-references")).toContainText("Gale Crater floor (Aeolis Palus)");
  await expect(page.getByTestId("method-references")).toContainText("distances only");
  await expect(page.getByTestId("method-discrimination")).toContainText("Eberswalde crater delta");
  await expect(page.getByTestId("worked-example")).toContainText("exp(−ln 2");
  await expect(page.getByTestId("thermal-audit")).toContainText(/Spatial support/);
  await expectNoHorizontalOverflow(page);
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
  expect(payload.results.map((r) => [r.site_id, r.state, r.observed_index, r.rank])).toEqual(fixture.results.map((r) => [r.site_id, r.state, r.observed_index, r.rank]));
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
