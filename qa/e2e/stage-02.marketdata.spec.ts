import { expect, test, type Page } from "@playwright/test";
import { login, OWNER_PASSWORD } from "./helpers/auth";

/**
 * Stage 2 — Market data & scheduler (QA-2).
 * Verifies real DEMO candle ingest, connection status, the event ledger with
 * payload drawer, and write-only credential storage + connection test.
 */

async function gotoEvents(page: Page) {
  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: /event ledger/i }).click();
  await expect(page.getByTestId("view-title")).toHaveText("Event ledger");
}

test("QA-2.01 connection status shows Binance reachable and candles stored", async ({
  page,
}) => {
  await login(page);
  await gotoEvents(page);
  const status = page.getByTestId("connection-status");
  await expect(status).toContainText("Connected");
  // At least the startup backfill (hundreds of candles) is present.
  await expect(status).toContainText(/\d/);
});

test("QA-2.02 API reports real ingested candles with zero gaps", async ({
  page,
  request,
}) => {
  await login(page);
  // Reuse the browser's stored access token for a direct API assertion.
  const token = await page.evaluate(() => sessionStorage.getItem("cp_access"));
  const resp = await request.get("/api/market/status", {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  expect(body.candles_stored).toBeGreaterThan(100);
  expect(body.gaps).toBe(0);
  expect(body.exchange_reachable).toBe(true);
  expect(body.symbol).toBe("BTCUSDT");
});

test("QA-2.03 event ledger lists ingest events and opens payload drawer", async ({
  page,
}) => {
  await login(page);
  await gotoEvents(page);
  const table = page.getByTestId("events-table");
  // Search for the ingest event specifically (robust to other system events).
  await page.getByLabel("Search events").fill("candle ingest");
  await expect(table.locator(".category").first()).toHaveText("system");
  await table.getByRole("button").first().click();
  // Drawer shows the reconstructable ingest payload JSON.
  await expect(page.getByTestId("payload-json")).toBeVisible();
  await expect(page.getByTestId("payload-json")).toContainText(/reason|gaps/);
});

test("QA-2.04 event filters narrow the list", async ({ page }) => {
  await login(page);
  await gotoEvents(page);
  const chips = page.getByTestId("events-table").locator(".category");
  await page.getByLabel("Filter category").selectOption("security");
  // Wait for the filtered reload to settle, then assert every chip matches.
  await expect(chips.first()).toHaveText("security");
  const count = await chips.count();
  expect(count).toBeGreaterThan(0);
  for (let i = 0; i < count; i++) {
    await expect(chips.nth(i)).toHaveText("security");
  }
});

test("QA-2.05 manual candle ingest button works", async ({ page }) => {
  await login(page);
  await gotoEvents(page);
  await page.getByTestId("backfill-btn").click();
  // Status still shows connected + candles after re-ingest.
  await expect(page.getByTestId("connection-status")).toContainText(
    "Connected",
  );
});

test("QA-2.06 credentials are write-only: saved key shows masked hint, secret never returned", async ({
  page,
}) => {
  await login(page);
  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: /settings/i }).click();
  await expect(page.getByTestId("view-title")).toHaveText("Settings");

  await page.getByLabel("DEMO API key").fill("DEMOKEYABCD1234WXYZ");
  await page.getByLabel("DEMO API secret").fill("ultra-secret-demo-value");
  await page.getByLabel("DEMO current password").fill(OWNER_PASSWORD);
  await page
    .getByTestId("credential-DEMO")
    .getByRole("button", { name: /save credentials/i })
    .click();

  await expect(page.getByTestId("cred-state-DEMO")).toContainText(
    /configured/i,
  );
  await expect(page.getByTestId("cred-state-DEMO")).toContainText("WXYZ");
  // The plaintext secret must never appear anywhere in the DOM.
  await expect(page.locator("body")).not.toContainText(
    "ultra-secret-demo-value",
  );
});

test("QA-2.07 connection test reports public reachability", async ({
  page,
}) => {
  await login(page);
  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: /settings/i }).click();
  await page
    .getByTestId("credential-LIVE")
    .getByRole("button", { name: /test connection/i })
    .click();
  await expect(page.getByTestId("test-result-LIVE")).toBeVisible();
});
