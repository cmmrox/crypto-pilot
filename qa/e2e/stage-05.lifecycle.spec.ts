import { expect, test, type Page } from "@playwright/test";
import { login } from "./helpers/auth";

/**
 * Stage 5 — Bot lifecycle & Overview (QA-5).
 * Verifies the Overview renders live account truth and the guarded control flow
 * (start reconciles, stop leaves position, kill needs typed FLATTEN). Requires
 * DEMO credentials stored in the app DB (bot start reconciles the real account).
 */

const HAS_DEMO_CREDENTIALS = Boolean(
  process.env.CP_BINANCE_DEMO_KEY && process.env.CP_BINANCE_DEMO_SECRET,
);
test.describe.configure({ mode: "serial" });

async function ensureStopped(page: Page) {
  await expect(page.getByTestId("market-panel")).toBeVisible({
    timeout: 15_000,
  });
  const status = page.getByTestId("bot-status");
  await expect(status).toBeVisible();
  if (!/stopped/i.test((await status.textContent()) ?? "")) {
    await page.getByTestId("stop-btn").click();
    await page.getByRole("button", { name: /stop, leave position/i }).click();
    await expect(status).toContainText(/stopped/i, { timeout: 15000 });
  }
}

test("QA-5.01 Overview renders live account truth", async ({ page }) => {
  test.skip(!HAS_DEMO_CREDENTIALS, "DEMO credentials not set in env");
  await login(page);
  // Balance from the real DEMO account (funded), so a positive dollar amount shows.
  await expect(page.getByText("Account balance")).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByTestId("breaker-panel")).toContainText(
    /circuit breakers/i,
  );
  await expect(page.getByTestId("breaker-long")).toBeVisible();
  await expect(page.getByTestId("breaker-short")).toBeVisible();
});

test("QA-5.02 start reconciles and runs; stop returns to stopped", async ({
  page,
}) => {
  test.skip(!HAS_DEMO_CREDENTIALS, "DEMO credentials not set in env");
  await login(page);
  await ensureStopped(page);
  await page.getByTestId("start-btn").click();
  await expect(page.getByRole("heading", { name: /start on/i })).toBeVisible();
  await page.getByRole("button", { name: /reconcile & start/i }).click();
  await expect(page.getByTestId("bot-status")).toContainText(
    /running|safe mode/i,
    { timeout: 15000 },
  );

  await page.getByTestId("stop-btn").click();
  await page.getByRole("button", { name: /stop, leave position/i }).click();
  await expect(page.getByTestId("bot-status")).toContainText(/stopped/i, {
    timeout: 15000,
  });
});

test("QA-5.03 kill switch requires typing FLATTEN", async ({ page }) => {
  test.skip(!HAS_DEMO_CREDENTIALS, "DEMO credentials not set in env");
  await login(page);
  await page.getByTestId("kill-btn").click();
  const confirm = page.getByRole("button", { name: /flatten & stop/i });
  // Disabled until the exact word is typed.
  await expect(confirm).toBeDisabled();
  await page.getByLabel(/type flatten to confirm/i).fill("FLATTEN");
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(page.getByTestId("toast")).toContainText(/kill switch/i, {
    timeout: 15000,
  });
});

test("QA-5.04 modal cancel makes no change", async ({ page }) => {
  test.skip(!HAS_DEMO_CREDENTIALS, "DEMO credentials not set in env");
  await login(page);
  await ensureStopped(page);
  await page.getByTestId("start-btn").click();
  await page.getByRole("button", { name: /^cancel$/i }).click();
  // Still stopped — cancel did nothing.
  await expect(page.getByTestId("bot-status")).toContainText(/stopped/i);
});

test("QA-5.05 worker heartbeat and dependencies are explicit", async ({
  page,
}) => {
  await login(page);
  const rail = page.getByTestId("engine-status-rail");
  await expect(rail).toBeVisible();
  await expect(rail).toContainText(/background worker/i);
  await expect(page.getByTestId("heartbeat-age")).toContainText(/heartbeat/i);
  await expect(rail).toContainText(/scheduler/i);
  await expect(rail).toContainText(/database/i);
  await expect(rail).toContainText(/market feed/i);
});

test("QA-5.06 pair, timeframe, current mark and freshness are visible", async ({
  page,
}) => {
  await login(page);
  const market = page.getByTestId("market-panel");
  await expect(market).toBeVisible();
  await expect(market).toContainText("BTCUSDT");
  await expect(market).toContainText("4h");
  await expect(market).toContainText(/mark price/i);
  await expect(market).toContainText(/live|stale/i);
});

test("QA-5.07 next closed-candle window and strategy conditions are visible", async ({
  page,
}) => {
  await login(page);
  await expect(page.getByTestId("decision-countdown")).toHaveText(
    /^\d{2}:\d{2}:\d{2}$/,
  );
  const watch = page.getByTestId("strategy-watch-panel");
  await expect(watch).toContainText(/closed 4h/i);
  await expect(watch).toContainText(/not a guaranteed trade/i);
});

test("QA-5.08 news briefing is visible and explicitly isolated", async ({
  page,
}) => {
  await login(page);
  const news = page.getByTestId("news-briefing-panel");
  await expect(news).toBeVisible();
  await expect(page.getByTestId("news-isolation-notice")).toContainText(
    /never a trading input/i,
  );
  await expect(news.getByRole("link", { name: /open news briefing/i })).toBeVisible();
});

test("QA-5.09 refresh failure keeps state and marks it stale", async ({
  page,
}) => {
  await login(page);
  await expect(page.getByTestId("market-panel")).toBeVisible();
  await page.route("**/api/overview", (route) => route.abort("failed"));
  await expect(page.getByTestId("overview-refresh-error")).toBeVisible({
    timeout: 8_000,
  });
  await expect(page.getByTestId("market-panel")).toBeVisible();
});
