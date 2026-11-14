import { expect, test } from "@playwright/test";

const apiBase = "http://127.0.0.1:8100";

function collectBrowserErrors(page: import("@playwright/test").Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("Attempted to synchronously unmount a root while React was already rendering")) errors.push(message.text());
  });
  return errors;
}

test("isolated build identity, real catalog, planned sites, and navigation", async ({ page, request }) => {
  const errors = collectBrowserErrors(page);
  await page.goto("/");
  await expect(page.locator("main[data-application-id='alterecho-terrain-explorer']")).toHaveAttribute("data-build-identifier", "phase5-e2e");
  const health = await request.get(`${apiBase}/api/health`);
  expect(health.ok()).toBeTruthy();
  const healthPayload = await health.json();
  expect(healthPayload.build_identifier).toBe("phase5-e2e");
  expect(healthPayload.data_counts.rankable_real_earth_candidates).toBe(3);
  expect(healthPayload.data_counts.production_demo_sites).toBe(0);
  await expect(page.getByText(/ONLINE · 3 REAL EARTH CANDIDATES|3 real Earth sites available/)).toBeVisible();
  for (const id of ["earth-atacama", "earth-upper-mustang", "earth-ladakh"]) await expect(page.getByTestId(`candidate-${id}`)).toBeVisible();
  await expect(page.getByText(/Demo preview/)).toHaveCount(0);
  await page.getByRole("button", { name: /^Planned/ }).click();
  for (const id of ["earth-holuhraun", "earth-mcmurdo-dry-valleys"]) {
    const card = page.getByTestId(`candidate-${id}`);
    await expect(card).toBeVisible();
    await expect(card.getByRole("checkbox")).toBeDisabled();
    await expect(card).toContainText("Planned dataset integration");
  }
  await page.getByRole("button", { name: /^All sites/ }).click();
  await page.getByRole("button", { name: /Danakil Depression/ }).click();
  await expect(page.getByTestId("selected-candidate-details")).toContainText("Danakil Depression");
  await expect(page.getByTestId("candidate-earth-danakil").getByRole("checkbox")).toBeDisabled();
  await page.getByRole("button", { name: /Real data/ }).click();
  await expect(page.getByTestId("candidate-earth-upper-mustang")).toBeVisible();
  await expect(page.getByTestId("candidate-earth-danakil")).toHaveCount(0);
  await page.getByRole("button", { name: /^All/ }).click();

  const navigation = page.getByRole("navigation", { name: "Main navigation" });
  await navigation.getByRole("button", { name: "Planetary explorer" }).click();
  await expect(page.getByTestId("planetary-explorer-view")).toBeVisible();
  await expect(page.getByTestId("candidate-earth-atacama")).toHaveCount(0);
  await navigation.getByRole("button", { name: "Analogue discovery" }).click();
  await expect(page.getByTestId("candidate-earth-atacama")).toBeVisible();
  await expect(page.getByTestId("results-panel")).toHaveCount(0);
  await navigation.getByRole("button", { name: "Comparison lab" }).click();
  await expect(page.getByTestId("comparison-lab-view")).toBeVisible();
  await page.getByRole("button", { name: "Edit site selection" }).click();
  await expect(page.getByTestId("candidate-earth-atacama")).toBeVisible();

  await navigation.getByRole("button", { name: "Planetary explorer" }).click();
  await page.getByRole("button", { name: "Mars" }).click();
  await expect(page.getByText("PLANETARY REFERENCE · PROCESSED TERRAIN")).toBeVisible();
  await page.getByRole("button", { name: "Mars" }).click();
  await expect(page.getByText(/PLANETARY REFERENCE · PROCESSED TERRAIN/)).toBeVisible();
  const marsViewer = page.getByTestId("imagery-viewer");
  await expect(marsViewer).toContainText("Jezero Crater · 2D AOI viewer");
  await expect(marsViewer).toContainText("JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0");
  await expect(marsViewer.getByRole("img", { name: /exact Jezero Crater study AOI/ })).toBeVisible();
  await page.getByRole("button", { name: "Moon" }).click();
  await expect(page.getByRole("heading", { name: "Interactive lunar surface" })).toBeVisible();
  await navigation.getByRole("button", { name: "Research assistant" }).click();
  await expect(page.getByRole("button", { name: "Assistant unavailable" })).toBeDisabled();
  await navigation.getByRole("button", { name: "Mission planner" }).click();
  await expect(page.getByRole("heading", { name: "Mars terrain analogue study" })).toBeVisible();
  await navigation.getByRole("button", { name: "Scientific data" }).click();
  await expect(page.getByRole("heading", { name: "Source manifests" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("real index, provenance, synchronized focus, stale-result clearing, and JSON download", async ({ page }) => {
  const errors = collectBrowserErrors(page);
  await page.goto("/");
  await expect(page.getByTestId("selected-candidate-details")).toContainText("Atacama Desert");
  await expect(page.getByTestId("selected-candidate-details")).toContainText("earth-atacama-aoi-v1");
  await page.getByRole("button", { name: "Compare 3 sites" }).click();
  await expect(page.getByTestId("comparison-lab-view")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Comparison lab" })).toHaveAttribute("aria-current", "page");
  const result = page.getByTestId("result-earth-atacama");
  await expect(result).toContainText("Terrain Analogy Index");
  await expect(result).toContainText("96.1/100");
  await expect(result).toContainText("not a probability");
  await expect(result).toContainText("PROCESSED DEM");
  await expect(result).toContainText("Processing runs:");
  await expect(result).toContainText("terrain-v3.0");
  const downloadPromise = page.waitForEvent("download");
  await result.getByRole("button", { name: "Download result JSON" }).click();
  const download = await downloadPromise;
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  const payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  expect(payload.comparison_classification).toBe("real_comparison");
  expect(payload.provenance.notice).toMatch(/integrity-checked processed elevation datasets/);

  const navigation = page.getByRole("navigation", { name: "Main navigation" });
  await navigation.getByRole("button", { name: "Research reports" }).click();
  const reportDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export report JSON" }).click();
  const report = await reportDownload;
  expect(report.suggestedFilename()).toMatch(/terraluna-research-report-.*\.json/);

  await navigation.getByRole("button", { name: "Analogue discovery" }).click();
  await page.getByRole("button", { name: /Upper Mustang/ }).click();
  await expect(page.getByTestId("candidate-earth-upper-mustang")).toHaveClass(/focused/);
  await expect(page.getByTestId("result-earth-atacama")).toHaveCount(0);
  await navigation.getByRole("button", { name: "Comparison lab" }).click();
  await expect(page.getByTestId("selected-candidate-details")).toContainText("Upper Mustang");
  expect(errors).toEqual([]);
});

test("exact AOI imagery modes are honest and rapid site switching does not leave stale metadata", async ({ page }) => {
  const errors = collectBrowserErrors(page);
  await page.goto("/");
  const viewer = page.getByTestId("imagery-viewer");
  await expect(viewer).toContainText("Atacama Desert · 2D AOI viewer");
  await expect(viewer).toContainText("verified local crop");
  await expect(viewer.getByRole("img", { name: /True-colour satellite crop for the exact Atacama Desert study AOI/ })).toBeVisible();
  await viewer.getByRole("tab", { name: "Latest available observation" }).click();
  await expect(viewer).toContainText("VIIRS_NOAA20_CorrectedReflectance_TrueColor");
  await expect(viewer).toContainText("2026-11-14");
  await expect(viewer.getByRole("img", { name: /Latest available observation for the exact Atacama Desert AOI/ })).toBeVisible();
  await viewer.getByRole("tab", { name: "3D Terrain" }).click();
  await expect(viewer.getByRole("img", { name: /Derived terrain visualization for the exact Atacama Desert study AOI/ })).toBeVisible();
  await viewer.getByRole("tab", { name: "Globe" }).click();
  await expect(viewer).toContainText("Open Planetary Explorer for the interactive Earth globe");
  await page.getByRole("button", { name: /Upper Mustang/ }).click();
  await page.getByRole("button", { name: /^Ladakh/ }).click();
  await expect(viewer).toContainText("Ladakh · 2D AOI viewer");
  await expect(viewer).not.toContainText("Upper Mustang · 2D AOI viewer");
  await expect(viewer).toContainText("authentication required");
  await viewer.getByRole("tab", { name: "3D Terrain" }).click();
  await expect(viewer.getByRole("img", { name: /Derived terrain visualization for the exact Ladakh study AOI/ })).toBeVisible();
  expect(errors).toEqual([]);
});

test("historical terrain-v2 remains explicitly selectable", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Method").selectOption("terrain-v2.0");
  await page.getByRole("button", { name: "Compare 3 sites" }).click();
  const result = page.getByTestId("result-earth-atacama");
  await expect(result).toContainText("Historical terrain-shape similarity index");
  await expect(result).toContainText("99.6/100");
  await expect(result).toContainText("terrain-v2.0");
});

test("API unavailable state never shows fixture results", async ({ page }) => {
  await page.route(`${apiBase}/api/**`, (route) => route.abort());
  await page.goto("/");
  await expect(page.getByText("Backend unavailable", { exact: true })).toBeVisible();
  await expect(page.getByText(/Could not load the candidate catalog|No sites match these filters/).first()).toBeVisible();
  await expect(page.locator("[data-testid^='result-']")).toHaveCount(0);
});

test("comparison failure preserves real selection and offers retry", async ({ page }) => {
  await page.route(`${apiBase}/api/discover`, (route) => route.abort());
  await page.goto("/");
  await page.getByRole("button", { name: "Compare 3 sites" }).click();
  await expect(page.getByText("Comparison request failed.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry comparison" })).toBeVisible();
  await expect(page.getByText("3 real sites selected")).toBeVisible();
  await expect(page.locator("[data-testid^='result-']")).toHaveCount(0);
});

test("tablet and mobile layouts do not overflow horizontally", async ({ page }) => {
  for (const viewport of [{ width: 1024, height: 768 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.locator("main.app-shell")).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});
