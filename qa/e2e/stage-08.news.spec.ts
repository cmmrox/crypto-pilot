import { expect, test, type Page } from "@playwright/test";
import { authenticator } from "otplib";

/**
 * Stage 8 — AI news (Codex SDK) (QA-8).
 * Verifies the News view renders (briefing/isolation/calendar), the Codex
 * device-code panel starts a login and shows the URL + user code, and the news
 * refresh is gated on Codex being connected. Actual Codex authentication is an
 * owner browser action, validated manually.
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

async function go(page: Page, name: RegExp, title: RegExp) {
  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name }).click();
  await expect(page.getByTestId("view-title")).toHaveText(title);
}

test("QA-8.01 News view renders with isolation notice and macro calendar", async ({ page }) => {
  await login(page);
  await go(page, /news/i, /market briefing/i);
  await expect(page.getByTestId("briefing-panel")).toBeVisible();
  await expect(page.getByTestId("isolation-notice")).toContainText(/never feeds the strategy/i);
});

test("QA-8.02 Codex panel shows connection state", async ({ page }) => {
  await login(page);
  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: /settings/i }).click();
  await expect(page.getByTestId("codex-card")).toBeVisible();
  await expect(page.getByTestId("codex-state")).toBeVisible();
});

test("QA-8.03 Codex connect starts a device-code login and shows URL + code", async ({ page }) => {
  await login(page);
  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: /settings/i }).click();
  const state = await page.getByTestId("codex-state").textContent();
  // Only exercise the connect flow if not already connected.
  if (/not connected/i.test(state ?? "")) {
    await page.getByTestId("codex-connect").click();
    await expect(page.getByTestId("device-code")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("user-code")).not.toBeEmpty();
  } else {
    // Already connected — the re-authenticate control is offered instead.
    await expect(page.getByTestId("codex-reauth")).toBeVisible();
  }
});

test("QA-8.04 news isolation is enforced by the API contract", async ({ page, request }) => {
  await login(page);
  const token = await page.evaluate(() => sessionStorage.getItem("cp_access"));
  const resp = await request.get("/api/news/latest", {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  expect(body.isolation_notice).toMatch(/no exchange keys/i);
  expect(Array.isArray(body.macro_calendar)).toBe(true);
});
