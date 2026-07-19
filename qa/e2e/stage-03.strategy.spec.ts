import { expect, test, type Page } from "@playwright/test";
import { login } from "./helpers/auth";

/**
 * Stage 3 — Strategy engine & parity (QA-3, UI slice).
 * The bar-for-bar parity gate runs in the backend CI (tests/parity). These E2E
 * checks verify the strategy library surfaces both validated releases with their
 * parity status and manifest.
 */

async function gotoSettings(page: Page) {
  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: /settings/i }).click();
  await expect(page.getByTestId("view-title")).toHaveText("Settings");
}

test("QA-3.01 strategy library shows both validated releases", async ({
  page,
}) => {
  await login(page);
  await gotoSettings(page);
  await expect(page.getByTestId("strategy-library")).toBeVisible();
  await expect(page.getByTestId("strategy-trend_rider_v6")).toContainText(
    "trend_rider_v6",
  );
  await expect(page.getByTestId("strategy-trend_rider_v6")).toContainText(
    "LONG + SHORT",
  );
  await expect(page.getByTestId("strategy-trend_rider_v52")).toContainText(
    "LONG ONLY",
  );
});

test("QA-3.02 v6 is active and parity-verified", async ({ page }) => {
  await login(page);
  await gotoSettings(page);
  await expect(page.getByTestId("parity-trend_rider_v6")).toContainText(
    /parity verified/i,
  );
  await expect(page.getByTestId("strategy-trend_rider_v6")).toContainText(
    "Active",
  );
});

test("QA-3.03 strategies API returns the validated manifest", async ({
  page,
  request,
}) => {
  await login(page);
  const token = await page.evaluate(() => sessionStorage.getItem("cp_access"));
  const resp = await request.get("/api/strategies", {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(resp.ok()).toBeTruthy();
  const byName = Object.fromEntries(
    (await resp.json()).map((s: { name: string }) => [s.name, s]),
  );
  expect(byName["trend_rider_v6"].parity_verified).toBe(true);
  expect(byName["trend_rider_v6"].params.stop_atr).toBe(2.5);
  expect(byName["trend_rider_v6"].warmup_bars).toBe(200);
});
