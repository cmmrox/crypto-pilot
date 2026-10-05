import { expect, test } from "@playwright/test";
import { login } from "./helpers/auth";

for (const side of ["LONG", "SHORT"] as const) {
  test(`AP-01 ${side} shows confirmed stop and partial target across reload`, async ({
    page,
  }) => {
    await login(page);
    await page.route("**/api/overview", async (route) => {
      const response = await route.fetch();
      const snapshot = await response.json();
      snapshot.position = {
        side,
        qty: "0.004",
        entry_price: "60000",
        mark_price: "61000",
        unrealized_pnl: "4",
        leverage: "1.2",
        has_price_stop: true,
        protection_confirmed: true,
        protection_checked_at: new Date().toISOString(),
        stop_policy: "required",
        stop_price: side === "LONG" ? "59000" : "61000",
        stop_qty: "0.004",
        stop_status: "NEW",
        stop_working_type: "CONTRACT_PRICE",
        original_stop_price: side === "LONG" ? "59000" : "61000",
        tp1_price: side === "LONG" ? "62000" : "58000",
        tp1_qty: "0.0016",
        tp1_filled_qty: "0",
        tp1_percent: "40.00",
        tp1_status: "NEW",
        exit_stage: "initial",
      };
      await route.fulfill({ response, json: snapshot });
    });
    await page.goto("/overview");
    const panel = page.getByTestId("position-protection");
    await expect(panel).toContainText("Current stop loss");
    await expect(panel).toContainText("Take profit 1");
    await expect(panel).toContainText("0.0016 BTC (40.00%)");
    await expect(panel).toContainText("Traded-price trigger");
    await expect(page.getByTestId("no-stop-callout")).toHaveCount(0);
    await page.reload();
    await expect(panel).toContainText("Original stop");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await panel.screenshot({
      path: `test-results/atlas-${side.toLowerCase()}-${test.info().project.name}.png`,
    });
  });
}

test("AP-02 missing protection is explicit on a required-stop strategy", async ({
  page,
}) => {
  await login(page);
  await page.route("**/api/overview", async (route) => {
    const response = await route.fetch();
    const snapshot = await response.json();
    snapshot.position = {
      side: "SHORT",
      qty: "0.004",
      entry_price: "60000",
      mark_price: "60000",
      unrealized_pnl: "0",
      leverage: "1.2",
      has_price_stop: false,
      stop_policy: "required",
      protection_confirmed: false,
      protection_checked_at: null,
      stop_price: null,
      stop_qty: null,
      stop_status: null,
      stop_working_type: null,
      original_stop_price: null,
      tp1_price: null,
      tp1_qty: null,
      tp1_filled_qty: null,
      tp1_percent: null,
      tp1_status: null,
      exit_stage: "unverified",
    };
    await route.fulfill({ response, json: snapshot });
  });
  await page.goto("/overview");
  await expect(
    page.getByRole("alert").filter({ hasText: "Stop protection is missing" }),
  ).toBeVisible();
  await expect(page.getByTestId("no-stop-callout")).toHaveCount(0);
});

test("AP-03 trade detail shows target prices, quantities and fill facts", async ({
  page,
}) => {
  await login(page);
  await page.route("**/api/trades/-6002", async (route) => {
    const response = await route.fetch();
    const trade = await response.json();
    trade.strategy = "atlas_dual_v1_4h";
    trade.strategy_release = "1.2";
    trade.remaining_qty = "0.0024";
    trade.orders = [
      {
        client_order_id: "QA-ATLAS-STOP",
        binance_order_id: "qa-only",
        type: "STOP_MARKET",
        status: "NEW",
        qty: "0.0024",
        price: null,
        stop_price: "60000",
        reduce_only: true,
        filled_qty: "0",
        avg_fill_px: null,
        placed_at: new Date().toISOString(),
        filled_at: null,
        working_type: "CONTRACT_PRICE",
      },
      {
        client_order_id: "QA-ATLAS-TP1",
        binance_order_id: "qa-only-tp",
        type: "LIMIT",
        status: "FILLED",
        qty: "0.0016",
        price: "58000",
        stop_price: null,
        reduce_only: true,
        filled_qty: "0.0016",
        avg_fill_px: "58000",
        placed_at: new Date().toISOString(),
        filled_at: new Date().toISOString(),
        working_type: null,
      },
    ];
    await route.fulfill({ response, json: trade });
  });
  await page.goto("/trades");
  await page
    .getByRole("button", { name: "Trade -6002 detail", exact: true })
    .click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toContainText("stop $60,000.00");
  await expect(drawer).toContainText("target $58,000.00");
  await expect(drawer).toContainText("filled 0.0016 BTC");
  await expect(drawer).not.toContainText("No short price stop");
});
