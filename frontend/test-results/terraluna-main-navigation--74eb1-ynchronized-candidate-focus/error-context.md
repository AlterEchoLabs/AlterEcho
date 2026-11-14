# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: terraluna.spec.ts >> main navigation, health, filters, and synchronized candidate focus
- Location: e2e\terraluna.spec.ts:3:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByTestId('candidate-earth-atacama')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" getByTestId('candidate-earth-atacama') with timeout 5000ms
  - waiting for getByTestId('candidate-earth-atacama')

```

```yaml
- img
- heading "This page couldn’t load" [level=1]
- paragraph: Reload to try again, or go back.
- button "Reload"
- button "Back"
```

# Test source

```ts
  1   | import { expect, test } from "@playwright/test";
  2   | 
  3   | test("main navigation, health, filters, and synchronized candidate focus", async ({ page, request }) => {
  4   |   const errors: string[] = [];
  5   |   page.on("pageerror", (error) => errors.push(error.message));
  6   |   await page.goto("/");
  7   |   await expect(page.getByText("3 real Earth sites available")).toBeVisible();
  8   |   const health = await request.get("http://127.0.0.1:8000/api/health");
  9   |   expect(health.ok()).toBeTruthy();
  10  |   expect((await health.json()).data_mode).toBe("mixed");
  11  |   await expect(page.getByTestId("candidate-earth-atacama")).toBeVisible();
  12  | 
  13  |   await page.getByRole("button", { name: /Upper Mustang/ }).click();
  14  |   await expect(page.getByTestId("selected-candidate-details").getByRole("heading", { name: "Upper Mustang" })).toBeVisible();
  15  |   await page.getByRole("button", { name: /^All/ }).click();
  16  |   await page.getByRole("button", { name: /Danakil Depression/ }).click();
  17  |   await expect(page.getByTestId("selected-candidate-details").getByRole("heading", { name: "Danakil Depression" })).toBeVisible();
  18  |   await expect(page.getByTestId("candidate-earth-danakil").getByRole("checkbox")).toBeDisabled();
  19  | 
  20  |   await page.getByRole("button", { name: /Real data/ }).click();
  21  |   await expect(page.getByTestId("candidate-earth-upper-mustang")).toBeVisible();
  22  |   await expect(page.getByTestId("candidate-earth-danakil")).toHaveCount(0);
  23  |   await page.getByRole("button", { name: /^All/ }).click();
  24  | 
  25  |   const navigation = page.getByRole("navigation", { name: "Main navigation" });
  26  |   await navigation.getByRole("button", { name: "Planetary explorer" }).click();
  27  |   await expect(page.getByTestId("planetary-explorer-view")).toBeVisible();
  28  |   await expect(page.getByTestId("candidate-earth-atacama")).toHaveCount(0);
  29  |   await navigation.getByRole("button", { name: "Analogue discovery" }).click();
  30  |   await expect(page.getByTestId("candidate-earth-atacama")).toBeVisible();
  31  |   await expect(page.getByTestId("results-panel")).toHaveCount(0);
  32  |   await navigation.getByRole("button", { name: "Comparison lab" }).click();
  33  |   await expect(page.getByTestId("comparison-lab-view")).toBeVisible();
  34  |   await page.getByRole("button", { name: "Edit site selection" }).click();
> 35  |   await expect(page.getByTestId("candidate-earth-atacama")).toBeVisible();
      |                                                             ^ Error: expect(locator).toBeVisible() failed
  36  | 
  37  |   await page.getByRole("button", { name: "Mars" }).click();
  38  |   await expect(page.getByText("PLANETARY REFERENCE · PROCESSED TERRAIN")).toBeVisible();
  39  |   await expect(page.getByTestId("mars-location-marker")).toBeVisible();
  40  |   await expect(page.getByTestId("mars-location-marker")).toContainText("Jezero Crater");
  41  |   await page.getByRole("button", { name: "Moon" }).click();
  42  |   await expect(page.getByRole("heading", { name: "Interactive lunar surface" })).toBeVisible();
  43  |   await navigation.getByRole("button", { name: "Research assistant" }).click();
  44  |   await expect(page.getByRole("button", { name: "Assistant unavailable" })).toBeDisabled();
  45  |   await navigation.getByRole("button", { name: "Mission planner" }).click();
  46  |   await expect(page.getByRole("heading", { name: "Mars terrain analogue study" })).toBeVisible();
  47  |   await navigation.getByRole("button", { name: "Scientific data" }).click();
  48  |   await expect(page.getByRole("heading", { name: "Source manifests" })).toBeVisible();
  49  |   expect(errors).toEqual([]);
  50  | });
  51  | 
  52  | test("real result is honest, clears on focus change, and downloads valid JSON", async ({ page }) => {
  53  |   await page.goto("/");
  54  |   await expect(page.getByTestId("candidate-earth-atacama")).toBeVisible();
  55  |   await expect(page.getByRole("button", { name: "Compare 3 sites" })).toBeVisible();
  56  |   await page.getByRole("button", { name: "Compare 3 sites" }).click();
  57  |   await expect(page.getByTestId("comparison-lab-view")).toBeVisible();
  58  |   await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Comparison lab" })).toHaveAttribute("aria-current", "page");
  59  |   const result = page.getByTestId("result-earth-atacama");
  60  |   await expect(result).toContainText("PROCESSED DEM");
  61  |   await expect(result).toContainText("Processing runs:");
  62  |   const downloadPromise = page.waitForEvent("download");
  63  |   await result.getByRole("button", { name: "Download result JSON" }).click();
  64  |   const download = await downloadPromise;
  65  |   const stream = await download.createReadStream();
  66  |   const chunks: Buffer[] = [];
  67  |   for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  68  |   const payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  69  |   expect(payload.comparison_classification).toBe("real_comparison");
  70  |   expect(payload.provenance.notice).toMatch(/processed elevation datasets/);
  71  | 
  72  |   const navigation = page.getByRole("navigation", { name: "Main navigation" });
  73  |   await navigation.getByRole("button", { name: "Research reports" }).click();
  74  |   const reportDownload = page.waitForEvent("download");
  75  |   await page.getByRole("button", { name: "Export report JSON" }).click();
  76  |   const report = await reportDownload;
  77  |   expect(report.suggestedFilename()).toMatch(/terraluna-research-report-.*\.json/);
  78  | 
  79  |   await navigation.getByRole("button", { name: "Analogue discovery" }).click();
  80  |   await page.getByRole("button", { name: /Upper Mustang/ }).click();
  81  |   await expect(page.getByTestId("candidate-earth-upper-mustang")).toHaveClass(/focused/);
  82  |   await expect(page.getByTestId("result-earth-atacama")).toHaveCount(0);
  83  |   await navigation.getByRole("button", { name: "Comparison lab" }).click();
  84  |   await expect(page.getByTestId("selected-candidate-details")).toContainText("Upper Mustang");
  85  | });
  86  | 
  87  | test("API unavailable state is understandable", async ({ page }) => {
  88  |   await page.route("http://localhost:8000/api/**", (route) => route.abort());
  89  |   await page.route("http://127.0.0.1:8000/api/**", (route) => route.abort());
  90  |   await page.goto("/");
  91  |   await expect(page.getByText("Backend unavailable", { exact: true })).toBeVisible();
  92  |   await expect(page.getByText(/Candidate catalog unavailable|No backend candidates/).first()).toBeVisible();
  93  | });
  94  | 
  95  | test("comparison failure preserves selection and offers retry", async ({ page }) => {
  96  |   await page.route("http://localhost:8000/api/discover", (route) => route.abort());
  97  |   await page.goto("/");
  98  |   await page.getByRole("button", { name: "Compare 3 sites" }).click();
  99  |   await expect(page.getByText("Comparison request failed.")).toBeVisible();
  100 |   await expect(page.getByRole("button", { name: "Retry comparison" })).toBeVisible();
  101 |   await expect(page.getByText("3 real sites selected")).toBeVisible();
  102 | });
  103 | 
```