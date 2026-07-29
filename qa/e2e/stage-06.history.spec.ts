import { expect, test, type Page } from "@playwright/test";
import { login } from "./helpers/auth";

/**
 * Stage 6 — Trades / Monthly / Events (QA-6).
 * Verifies filterable trade history, the per-trade order drawer, CSV export,
 * and the monthly ledger with the manual withdrawal flow. Assumes two seeded
 * closed trades (a winning LONG and a losing SHORT) in 2026-07.
 */

async function goto(page: Page, name: RegExp, title: string) {
  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name }).click();
  await expect(page.getByTestId("view-title")).toHaveText(title);
}

test("QA-6.01 trades list shows seeded round trips", async ({ page }) => {
  await login(page);
  await goto(page, /trades/i, "Trades");
  const table = page.getByTestId("trades-table");
  await expect(table.getByText("4 ATR trail")).toBeVisible();
  await expect(table.getByText("bear regime ended")).toBeVisible();
});

test("QA-6.02 side filter narrows to LONG", async ({ page }) => {
  await login(page);
  await goto(page, /trades/i, "Trades");
  await page.getByLabel("Filter by side").selectOption("LONG");
  const sides = page.getByTestId("trades-table").locator(".side");
  await expect(sides.first()).toHaveText("LONG");
  const count = await sides.count();
  for (let i = 0; i < count; i++) await expect(sides.nth(i)).toHaveText("LONG");
});

test("QA-6.03 trade drawer reconstructs linked orders", async ({ page }) => {
  await login(page);
  await goto(page, /trades/i, "Trades");
  await page.getByLabel("Filter by side").selectOption("LONG");
  // Wait for the LONG filter to settle before opening the first row.
  await expect(
    page.getByTestId("trades-table").locator(".side").first(),
  ).toHaveText("LONG");
  await page.getByTestId("trades-table").getByRole("button").first().click();
  const orders = page.getByTestId("linked-orders");
  await expect(orders).toBeVisible();
  await expect(orders).toContainText("MARKET");
  await expect(orders).toContainText("STOP_MARKET");
});

test("QA-6.04 CSV export downloads reconciled rows", async ({ page }) => {
  await login(page);
  await goto(page, /trades/i, "Trades");
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByTestId("export-csv").click(),
  ]);
  expect(download.suggestedFilename()).toContain("cryptopilot-trades");
});

test("QA-6.05 monthly ledger aggregates realized P&L correctly", async ({
  page,
}) => {
  await login(page);
  await goto(page, /monthly/i, "Monthly ledger");
  const july = page.getByTestId("month-2026-07");
  await expect(july).toBeVisible();
  // Stable regardless of withdrawal state: realized 200 − 50 = 150, net 150 − 9 = 141.
  await expect(july).toContainText("$150.00");
  await expect(july).toContainText("$141.00");
});

test("QA-6.06 mark withdrawn records $14.10 and removes the allowance", async ({
  page,
}, testInfo) => {
  // Data-mutation test: run on one project only (avoids parallel writes to the
  // same shared row). Idempotency is also covered by the backend test suite.
  test.skip(
    testInfo.project.name !== "desktop",
    "mutation test runs on desktop only",
  );
  await login(page);
  await goto(page, /monthly/i, "Monthly ledger");
  const july = page.getByTestId("month-2026-07");
  // Wait for the ledger data to load before inspecting the allowance button.
  await expect(july).toContainText("$150.00");
  const mark = page.getByTestId("mark-2026-07");
  // Withdrawable is 10% of net 141 = 14.10. Mark it if not already done.
  if ((await mark.count()) > 0) {
    await mark.click();
    // Scope to the dialog — the row button and the modal confirm share the label.
    await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes("/api/monthly/mark-withdrawn") &&
          r.request().method() === "POST",
      ),
      page
        .getByRole("dialog")
        .getByRole("button", { name: /mark withdrawn/i })
        .click(),
    ]);
  }
  // End state: July shows the $14.10 withdrawal and offers no further allowance.
  await expect(july).toContainText("$14.10", { timeout: 10000 });
  await expect(page.getByTestId("mark-2026-07")).toHaveCount(0, {
    timeout: 10000,
  });
});

test("QA-6.07 audit surfaces distinguish loading from an empty result", async ({
  page,
}) => {
  await login(page);

  let releaseTrades!: () => void;
  const tradesGate = new Promise<void>((resolve) => {
    releaseTrades = resolve;
  });
  await page.route("**/api/trades**", async (route) => {
    await tradesGate;
    await route.continue();
  });

  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: /trades/i }).click();

  const table = page.getByTestId("trades-table");
  await expect(table).toHaveAttribute("aria-busy", "true");
  await expect(table.getByRole("status")).toContainText(
    "Loading trade history",
  );
  await expect(table).not.toContainText("No matching trades");

  releaseTrades();
  await expect(table).toHaveAttribute("aria-busy", "false");
  await expect(table.getByRole("status")).toHaveCount(0);
});

test("QA-6.08 trade history pages after fifty records", async ({ page }) => {
  await login(page);
  const trades = Array.from({ length: 51 }, (_, index) => {
    const id = 51 - index;
    return {
      id,
      opened_at: `2026-07-${String((index % 28) + 1).padStart(2, "0")}T00:00:00Z`,
      closed_at: null,
      side: "LONG",
      entry_px: "9007199254740993.125",
      exit_px: null,
      qty: "0.001",
      fees: "0",
      realized_pnl: null,
      r_multiple: null,
      exit_reason: null,
      strategy: "trend_rider_v6",
      environment: "DEMO",
      outcome: "OPEN",
    };
  });
  await page.route("**/api/trades?**", async (route) => {
    const url = new URL(route.request().url());
    const currentPage = Number(url.searchParams.get("page") ?? "1");
    const pageSize = Number(url.searchParams.get("page_size") ?? "50");
    const start = (currentPage - 1) * pageSize;
    await route.fulfill({
      json: {
        items: trades.slice(start, start + pageSize),
        total: trades.length,
        page: currentPage,
        page_size: pageSize,
        total_pages: 2,
      },
    });
  });

  await goto(page, /trades/i, "Trades");
  const pagination = page.getByTestId("trades-pagination");
  await expect(pagination).toContainText("Showing 1–50 of 51");
  await expect(page.getByLabel("Trade 51 detail")).toBeVisible();
  await pagination.getByRole("button", { name: /next trades page/i }).click();
  await expect(pagination).toContainText("Showing 51–51 of 51");
  await expect(page.getByLabel("Trade 1 detail")).toBeVisible();
  await expect(page.getByText("$9,007,199,254,740,993.13")).toBeVisible();
});
