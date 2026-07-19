import { expect, test } from "@playwright/test";
import {
  differentOtp,
  latestOtp,
  login,
  loginThroughUi,
  OWNER_EMAIL as EMAIL,
  OWNER_PASSWORD as PASSWORD,
  passwordStep,
} from "./helpers/auth";

/**
 * Stage 1 — Authentication & app shell (QA-1).
 * Exercises the full login → SMS OTP → shell flow plus every failure path,
 * session revocation, route guards, and the API 401 sweep.
 *
 * Requires a test-mode stack and an owner provisioned with SMS 2FA:
 *   docker compose exec backend python -m app.cli create-owner \
 *     --email owner@cryptopilot.app --password 'PilotOwner!2026' \
 *     --phone 94711234567 --force
 */

/** On mobile the sidebar is off-canvas; open it so nav/sign-out are reachable. */
async function openNavIfMobile(page: import("@playwright/test").Page) {
  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) {
    await menu.click();
  }
}

test("QA-1.01 happy path: password + SMS OTP reaches the dashboard shell", async ({
  page,
}) => {
  await loginThroughUi(page);
  await expect(page.getByTestId("owner-email")).toContainText(EMAIL);
  await expect(page.getByTestId("view-title")).toHaveText("Overview");
});

test("QA-1.02 wrong password is rejected", async ({ page }) => {
  // Unique throwaway email per run so it never locks (owner counter untouched).
  await page.goto("/");
  await page.getByLabel("Email").fill(`nobody-${Date.now()}@cryptopilot.app`);
  await page.getByLabel("Password", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: /continue/i }).click();
  await expect(page.getByRole("alert")).toContainText(/invalid/i);
});

test("QA-1.03 wrong SMS OTP code is rejected", async ({ page }) => {
  const otpToken = await passwordStep(page);
  const actualCode = await latestOtp(page, otpToken);
  await page.getByLabel("Authentication code").fill(differentOtp(actualCode));
  await page.getByRole("button", { name: /verify & enter/i }).click();
  await expect(page.getByRole("alert")).toContainText(/incorrect|expired/i);
});

test("QA-1.10 otp_pending cannot access protected APIs or create a session", async ({
  page,
}) => {
  const otpToken = await passwordStep(page);
  const pending = { Authorization: `Bearer ${otpToken}` };

  expect(
    await page.evaluate(() => ({
      access: sessionStorage.getItem("cp_access"),
      refresh: sessionStorage.getItem("cp_refresh"),
    })),
  ).toEqual({ access: null, refresh: null });
  await expect(page.getByTestId("environment-badge")).toHaveCount(0);

  for (const path of [
    "/api/auth/me",
    "/api/overview",
    "/api/settings/security",
  ]) {
    expect((await page.request.get(path, { headers: pending })).status()).toBe(
      401,
    );
  }
  expect(
    (
      await page.request.post("/api/bot/start", {
        headers: pending,
      })
    ).status(),
  ).toBe(401);
  expect(
    (
      await page.request.post("/api/settings/security/2fa/start", {
        headers: pending,
        data: { password: PASSWORD, action: "disable" },
      })
    ).status(),
  ).toBe(401);
  expect(
    (
      await page.request.post("/api/auth/refresh", {
        data: { refresh_token: otpToken },
      })
    ).status(),
  ).toBe(401);
});

test("QA-1.11 resend remains cooldown-guarded by the server", async ({
  page,
}) => {
  await page.clock.install();
  await passwordStep(page);
  const resend = page.getByTestId("resend-otp");
  await expect(resend).toBeDisabled();

  // Advance only the browser clock. The backend's independent cooldown must
  // still reject the early resend and the UI must explain the throttle.
  await page.clock.fastForward(60_000);
  await expect(resend).toBeEnabled();
  await resend.click();
  await expect(page.getByRole("alert")).toContainText(
    /wait before requesting/i,
  );
  await expect(resend).toBeDisabled();
});

test("QA-1.12 post-issue identity failure leaves no browser session", async ({
  page,
}) => {
  const otpToken = await passwordStep(page);
  const code = await latestOtp(page, otpToken);
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "temporarily unavailable" }),
    }),
  );

  await page.getByLabel("Authentication code").fill(code);
  await page.getByRole("button", { name: /verify & enter/i }).click();
  await expect(page.getByRole("alert")).toContainText(
    /session could not be verified/i,
  );
  expect(
    await page.evaluate(() => ({
      access: sessionStorage.getItem("cp_access"),
      refresh: sessionStorage.getItem("cp_refresh"),
    })),
  ).toEqual({ access: null, refresh: null });
  await expect(page.getByTestId("environment-badge")).toHaveCount(0);
});

test("QA-1.04 unauthenticated user cannot reach the shell", async ({
  page,
}) => {
  await page.goto("/overview");
  // The app renders the login screen, not the dashboard.
  await expect(
    page.getByRole("heading", { name: /sign in securely/i }),
  ).toBeVisible();
  await expect(page.getByTestId("environment-badge")).toHaveCount(0);
});

test("QA-1.05 sign out returns to login and protects the shell", async ({
  page,
}) => {
  await login(page);
  await openNavIfMobile(page);
  await page.getByRole("button", { name: /sign out/i }).click();
  await expect(
    page.getByRole("heading", { name: /sign in securely/i }),
  ).toBeVisible();
  // Reloading does not restore the session.
  await page.reload();
  await expect(
    page.getByRole("heading", { name: /sign in securely/i }),
  ).toBeVisible();
});

test("QA-1.06 session persists across reload", async ({ page }) => {
  await login(page);
  await page.reload();
  await expect(page.getByTestId("environment-badge")).toBeVisible();
});

test("QA-1.07 sidebar navigation switches views", async ({ page }) => {
  await login(page);
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

test("QA-1.09 rate limit locks after repeated failures", async ({
  request,
}) => {
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
