import { expect, test, type Page } from "@playwright/test";
import { login } from "./helpers/auth";

/**
 * Stage 4 — Risk & execution (QA-4, live DEMO slice).
 * Stores the real DEMO credentials via the Settings UI, verifies authenticated
 * connectivity, runs a real DEMO round-trip through the ops self-check, and
 * confirms the resulting trade event surfaces in the audit ledger.
 *
 * DEMO key/secret come from the environment (never hardcoded). Skips if absent.
 */

const DEMO_KEY = process.env.CP_BINANCE_DEMO_KEY ?? "";
const DEMO_SECRET = process.env.CP_BINANCE_DEMO_SECRET ?? "";

test.skip(!DEMO_KEY || !DEMO_SECRET, "DEMO credentials not set in env");
// Live @exchange suite: places real DEMO orders. Run in its own pass (see
// qa/README.md) so it never overlaps the deterministic UI tests.
test.describe.configure({ mode: "serial" });

async function gotoSettings(page: Page) {
  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: /settings/i }).click();
  await expect(page.getByTestId("view-title")).toHaveText("Settings");
}

test("QA-4.01 store DEMO credentials and verify authenticated connection", async ({
  page,
}) => {
  await login(page);
  await gotoSettings(page);
  await page.getByLabel("DEMO API key").fill(DEMO_KEY);
  await page.getByLabel("DEMO API secret").fill(DEMO_SECRET);
  await page
    .getByTestId("credential-DEMO")
    .getByRole("button", { name: /save credentials/i })
    .click();
  await expect(page.getByTestId("cred-state-DEMO")).toContainText(
    /configured/i,
  );

  await page
    .getByTestId("credential-DEMO")
    .getByRole("button", { name: /test connection/i })
    .click();
  // With a valid key, the test performs a signed account call.
  await expect(page.getByTestId("test-result-DEMO")).toContainText(
    /account access verified/i,
  );
});

test("QA-4.02 live DEMO self-check round-trip reconciles and flattens", async ({
  page,
  request,
}) => {
  await login(page);
  const token = await page.evaluate(() => sessionStorage.getItem("cp_access"));
  const resp = await request.post("/api/ops/self-check-round-trip", {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 30000,
  });
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  expect(body.ok).toBe(true);
  expect(body.reconciled).toBe(true);
  expect(body.flattened).toBe(true);
});

test("QA-4.03 self-check trade event appears in the audit ledger", async ({
  page,
}) => {
  await login(page);
  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: /event ledger/i }).click();
  await expect(page.getByTestId("view-title")).toHaveText("Event ledger");
  await page.getByLabel("Search events").fill("self-check");
  await expect(
    page
      .getByTestId("events-table")
      .getByText(/execution self-check/i)
      .first(),
  ).toBeVisible();
});

test("QA-4.04 kill switch cancels orders and flattens (idempotent when flat)", async ({
  page,
  request,
}) => {
  await login(page);
  const token = await page.evaluate(() => sessionStorage.getItem("cp_access"));
  const resp = await request.post("/api/ops/kill", {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 30000,
  });
  expect(resp.ok()).toBeTruthy();
  expect((await resp.json()).ok).toBe(true);
});
