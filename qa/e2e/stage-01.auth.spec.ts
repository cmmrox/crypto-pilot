import { expect, test } from "@playwright/test";
import { authenticator } from "otplib";

/**
 * Stage 1 — Authentication & app shell (QA-1).
 * Exercises the full login → TOTP → shell flow plus every failure path,
 * session revocation, route guards, and the API 401 sweep.
 *
 * Requires the owner provisioned with the deterministic TOTP secret:
 *   docker compose exec backend python -m app.cli create-owner \
 *     --email owner@cryptopilot.app --password 'PilotOwner!2026' \
 *     --totp-secret JBSWY3DPEHPK3PXP --force
 */

const EMAIL = "owner@cryptopilot.app";
const PASSWORD = "PilotOwner!2026";
const TOTP_SECRET = "JBSWY3DPEHPK3PXP";

function code(): string {
  return authenticator.generate(TOTP_SECRET);
}

async function passwordStep(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: /continue/i }).click();
}

async function fullLogin(page: import("@playwright/test").Page) {
  await passwordStep(page);
  await expect(page.getByRole("heading", { name: /6-digit code/i })).toBeVisible();
  await page.getByLabel("Authentication code").fill(code());
  await page.getByRole("button", { name: /verify & enter/i }).click();
  await expect(page.getByTestId("environment-badge")).toBeVisible();
}

/** On mobile the sidebar is off-canvas; open it so nav/sign-out are reachable. */
async function openNavIfMobile(page: import("@playwright/test").Page) {
  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) {
    await menu.click();
  }
}

test("QA-1.01 happy path: password + TOTP reaches the dashboard shell", async ({ page }) => {
  await fullLogin(page);
  await expect(page.getByTestId("owner-email")).toContainText(EMAIL);
  await expect(page.getByTestId("view-title")).toHaveText("Overview");
});

test("QA-1.02 wrong password is rejected", async ({ page }) => {
  // Throwaway email so the owner's lockout counter is never polluted.
  await page.goto("/");
  await page.getByLabel("Email").fill("nobody@cryptopilot.app");
  await page.getByLabel("Password", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: /continue/i }).click();
  await expect(page.getByRole("alert")).toContainText(/invalid/i);
});

test("QA-1.03 wrong TOTP code is rejected", async ({ page }) => {
  await passwordStep(page);
  await page.getByLabel("Authentication code").fill("000000");
  await page.getByRole("button", { name: /verify & enter/i }).click();
  await expect(page.getByRole("alert")).toContainText(/invalid|expired/i);
});

test("QA-1.04 unauthenticated user cannot reach the shell", async ({ page }) => {
  await page.goto("/overview");
  // The app renders the login screen, not the dashboard.
  await expect(page.getByRole("heading", { name: /sign in securely/i })).toBeVisible();
  await expect(page.getByTestId("environment-badge")).toHaveCount(0);
});

test("QA-1.05 sign out returns to login and protects the shell", async ({ page }) => {
  await fullLogin(page);
  await openNavIfMobile(page);
  await page.getByRole("button", { name: /sign out/i }).click();
  await expect(page.getByRole("heading", { name: /sign in securely/i })).toBeVisible();
  // Reloading does not restore the session.
  await page.reload();
  await expect(page.getByRole("heading", { name: /sign in securely/i })).toBeVisible();
});

test("QA-1.06 session persists across reload", async ({ page }) => {
  await fullLogin(page);
  await page.reload();
  await expect(page.getByTestId("environment-badge")).toBeVisible();
});

test("QA-1.07 sidebar navigation switches views", async ({ page }) => {
  await fullLogin(page);
  await openNavIfMobile(page);
  await page.getByRole("link", { name: /event ledger/i }).click();
  await expect(page.getByTestId("view-title")).toHaveText("Event ledger");
  await openNavIfMobile(page);
  await page.getByRole("link", { name: /settings/i }).click();
  await expect(page.getByTestId("view-title")).toHaveText("Settings");
});

test("QA-1.08 API 401 sweep: protected endpoints reject anonymous requests", async ({
  request,
}) => {
  for (const path of ["/api/auth/me"]) {
    const resp = await request.get(path);
    expect(resp.status()).toBe(401);
  }
  // Logout and revoke-others also require auth.
  for (const path of ["/api/auth/logout", "/api/auth/sessions/revoke-others"]) {
    const resp = await request.post(path);
    expect(resp.status()).toBe(401);
  }
});

test("QA-1.09 rate limit locks after repeated failures", async ({ request }) => {
  // Unique throwaway email per run so repeated suite runs never lock the owner
  // and this test never interferes with the login tests.
  const email = `ratelimit-${Date.now()}@cryptopilot.app`;
  for (let i = 0; i < 5; i++) {
    const r = await request.post("/api/auth/login", {
      data: { email, password: "definitely-wrong" },
    });
    expect(r.status()).toBe(401);
  }
  const locked = await request.post("/api/auth/login", {
    data: { email, password: "definitely-wrong" },
  });
  expect(locked.status()).toBe(429);
});
