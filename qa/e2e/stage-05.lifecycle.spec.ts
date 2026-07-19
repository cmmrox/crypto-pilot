import { expect, test, type Page } from "@playwright/test";
import { login } from "./helpers/auth";

/**
 * Stage 5 — Bot lifecycle & Overview (QA-5).
 * Verifies the Overview renders live account truth and the guarded control flow
 * (start reconciles, stop leaves position, kill needs typed FLATTEN). Requires
 * DEMO credentials stored in the app DB (bot start reconciles the real account).
 */

// Bot start reconciles the real DEMO account, so this suite needs credentials.
test.skip(
  !process.env.CP_BINANCE_DEMO_KEY || !process.env.CP_BINANCE_DEMO_SECRET,
  "DEMO credentials not set in env",
);
test.describe.configure({ mode: "serial" });

async function ensureStopped(page: Page) {
  const status = page.getByTestId("bot-status");
  await expect(status).toBeVisible();
  if (!/stopped/i.test((await status.textContent()) ?? "")) {
    await page.getByTestId("stop-btn").click();
    await page.getByRole("button", { name: /stop, leave position/i }).click();
    await expect(status).toContainText(/stopped/i, { timeout: 15000 });
  }
}

test("QA-5.01 Overview renders live account truth", async ({ page }) => {
  await login(page);
  // Balance from the real DEMO account (funded), so a positive dollar amount shows.
  await expect(page.getByText("Account balance")).toBeVisible();
  await expect(page.getByTestId("breaker-panel")).toContainText(
    /circuit breakers/i,
  );
  await expect(page.getByTestId("breaker-long")).toBeVisible();
  await expect(page.getByTestId("breaker-short")).toBeVisible();
});

test("QA-5.02 start reconciles and runs; stop returns to stopped", async ({
  page,
}) => {
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
  await login(page);
  await ensureStopped(page);
  await page.getByTestId("start-btn").click();
  await page.getByRole("button", { name: /^cancel$/i }).click();
  // Still stopped — cancel did nothing.
  await expect(page.getByTestId("bot-status")).toContainText(/stopped/i);
});
