import { expect, test, type Page } from "@playwright/test";
import { authenticator } from "otplib";

/**
 * Stage 9 — Settings, security hardening & environment guard (QA-9).
 * Verifies security headers, the environment card + guarded LIVE switch (typed
 * confirm), guarded strategy selection, and the authz sweep. The tests never
 * commit a LIVE switch (which would break the DEMO-bound stack).
 */

const EMAIL = "owner@cryptopilot.app";
const PASSWORD = "PilotOwner!2026";
const TOTP_SECRET = "JBSWY3DPEHPK3PXP";

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: /continue/i }).click();
  await page.getByLabel("Authentication code").fill(authenticator.generate(TOTP_SECRET));
  await page.getByRole("button", { name: /verify & enter/i }).click();
  await expect(page.getByTestId("environment-badge")).toBeVisible();
}

async function gotoSettings(page: Page) {
  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: /settings/i }).click();
  await expect(page.getByTestId("view-title")).toHaveText("Settings");
}

test("QA-9.01 security headers are present", async ({ request }) => {
  const resp = await request.get("/health");
  const h = resp.headers();
  expect(h["x-content-type-options"]).toBe("nosniff");
  expect(h["x-frame-options"]).toBe("DENY");
  expect(h["content-security-policy"]).toContain("frame-ancestors 'none'");
});

test("QA-9.02 environment card shows DEMO active", async ({ page }) => {
  await login(page);
  await gotoSettings(page);
  await expect(page.getByTestId("environment-card")).toBeVisible();
  await expect(page.getByTestId("active-env")).toContainText("DEMO");
});

test("QA-9.03 switching to LIVE requires typing LIVE (cancelled here)", async ({ page }) => {
  await login(page);
  await gotoSettings(page);
  await page.getByTestId("env-live").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText(/type LIVE to confirm/i);
  const confirm = dialog.getByRole("button", { name: /switch to live/i });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel(/type LIVE to confirm/i).fill("LIVE");
  await expect(confirm).toBeEnabled();
  // Cancel — do NOT actually switch the running stack to LIVE.
  await dialog.getByRole("button", { name: /^cancel$/i }).click();
  await expect(page.getByTestId("active-env")).toContainText("DEMO");
});

test("QA-9.04 strategy fallback can be selected (guarded)", async ({ page }) => {
  await login(page);
  await gotoSettings(page);
  const select = page.getByTestId("select-trend_rider_v52");
  if ((await select.count()) > 0) {
    await select.click();
    await page.getByRole("dialog").getByRole("button", { name: /select release/i }).click();
    await expect(page.getByTestId("strategy-trend_rider_v52")).toContainText(/active/i);
    // Restore v6 as active.
    const back = page.getByTestId("select-trend_rider_v6");
    if ((await back.count()) > 0) {
      await back.click();
      await page.getByRole("dialog").getByRole("button", { name: /select release/i }).click();
    }
  }
  await expect(page.getByTestId("strategy-trend_rider_v6")).toBeVisible();
});

test("QA-9.05 authz sweep: protected APIs reject anonymous", async ({ request }) => {
  for (const p of ["/api/overview", "/api/trades", "/api/settings/sms"]) {
    expect((await request.get(p)).status()).toBe(401);
  }
  expect((await request.put("/api/settings/environment", { data: { environment: "DEMO" } })).status()).toBe(401);
});
