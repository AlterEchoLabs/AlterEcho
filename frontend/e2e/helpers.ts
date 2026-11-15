import type { Page } from "@playwright/test";

/** Below 960 px the links, reading mode and theme live in the menu; open it when it is collapsed. */
export async function openMenuIfCollapsed(page: Page) {
  const button = page.getByTestId("menu-button");
  if (await button.isVisible() && (await button.getAttribute("aria-expanded")) !== "true") await button.click();
}

export async function closeMenuIfOpen(page: Page) {
  const button = page.getByTestId("menu-button");
  if (await button.isVisible() && (await button.getAttribute("aria-expanded")) === "true") await button.click();
}

/** Switch the global reading mode (Simple / Detailed) from the masthead. */
export async function setDetail(page: Page, mode: "Simple" | "Detailed") {
  await openMenuIfCollapsed(page);
  await page.getByTestId("detail-toggle").getByRole("radio", { name: mode }).click();
  await closeMenuIfOpen(page);
}

/** Step 1: open the reference list and choose one. */
export async function pickReference(page: Page, id: string) {
  await page.getByTestId("reference-picker").click();
  await page.getByTestId(`reference-${id}`).click();
}
