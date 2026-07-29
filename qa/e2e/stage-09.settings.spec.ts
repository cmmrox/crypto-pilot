import { expect, test, type Page } from "@playwright/test";
import {
  createSession,
  differentOtp,
  latestOtpForChallenge,
  login,
  OWNER_EMAIL,
  OWNER_PASSWORD,
} from "./helpers/auth";

/**
 * Stage 9 — Settings, security hardening & environment guard (QA-9).
 * Verifies security headers, the environment card + guarded LIVE switch (typed
 * confirm), guarded strategy selection, and the authz sweep. The tests never
 * commit a LIVE switch (which would break the DEMO-bound stack).
 */

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

test("QA-9.03 switching to LIVE requires typing LIVE (cancelled here)", async ({
  page,
}) => {
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

test("QA-9.04 strategy fallback can be selected (guarded)", async ({
  page,
}) => {
  await login(page);
  await gotoSettings(page);
  const fallbackCard = page.getByTestId("strategy-trend_rider_v52_4h");
  const defaultCard = page.getByTestId("strategy-trend_rider_v6_4h");
  await expect(fallbackCard).toBeVisible();
  await expect(defaultCard).toBeVisible();

  const fallbackSelect = page.getByTestId("select-trend_rider_v52_4h");
  if ((await fallbackSelect.count()) > 0) {
    await fallbackSelect.click();
    const switched = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" &&
        response.url().endsWith("/api/settings/strategy"),
    );
    await page
      .getByRole("dialog")
      .getByRole("button", { name: /select release/i })
      .click();
    expect((await switched).ok()).toBeTruthy();
  }
  await expect(
    fallbackCard.getByText("Active", { exact: true }),
  ).toBeVisible();

  // Always restore the default so later tests do not inherit mutable state.
  const defaultSelect = page.getByTestId("select-trend_rider_v6_4h");
  await expect(defaultSelect).toBeVisible();
  await defaultSelect.click();
  const restored = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      response.url().endsWith("/api/settings/strategy"),
  );
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /select release/i })
    .click();
  expect((await restored).ok()).toBeTruthy();
  await expect(
    defaultCard.getByText("Active", { exact: true }),
  ).toBeVisible();
});

test("QA-9.05 authz sweep: protected APIs reject anonymous", async ({
  request,
}) => {
  for (const p of ["/api/overview", "/api/trades", "/api/settings/sms"]) {
    expect((await request.get(p)).status()).toBe(401);
  }
  expect(
    (
      await request.put("/api/settings/environment", {
        data: { environment: "DEMO" },
      })
    ).status(),
  ).toBe(401);
});

test("QA-9.06 disabling SMS 2FA is danger-guarded", async ({ page }) => {
  await login(page);
  await gotoSettings(page);
  await expect(page.getByTestId("twofa-card")).toBeVisible();
  await expect(page.getByTestId("twofa-state")).toContainText(/on/i);
  await page.getByTestId("twofa-toggle").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText(/password only/i);
  await expect(
    dialog.getByRole("button", { name: /continue to verification/i }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: /^cancel$/i }).click();
  await expect(page.getByTestId("twofa-state")).toContainText(/on/i);
});

test("QA-9.07 mobile-number change verifies the new number", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "security mutation runs once");
  const oldPhone = "94711234567";
  const newPhone = "94770000000";
  await login(page);
  await gotoSettings(page);

  const changePhone = async (phone: string) => {
    await page.getByTestId("twofa-change-phone").click();
    await page
      .getByLabel("Current password", { exact: true })
      .fill(OWNER_PASSWORD);
    await page.getByLabel("New mobile number").fill(phone);
    const startResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/settings/security/2fa/start") &&
        response.request().method() === "POST",
    );
    await page.getByTestId("twofa-send-code").click();
    const response = await startResponse;
    expect(response.ok()).toBeTruthy();
    const { challenge_id: challengeId } = (await response.json()) as {
      challenge_id: number;
    };
    await page
      .getByLabel("Verification code")
      .fill(await latestOtpForChallenge(page, challengeId));
    await page.getByTestId("twofa-confirm").click();
    await expect(page.getByTestId("twofa-result")).toContainText(
      /mobile number changed/i,
    );
    await expect(page.getByTestId("twofa-state")).toContainText(
      phone.slice(-4),
    );
  };

  await changePhone(newPhone);
  await changePhone(oldPhone);
});

test("QA-9.08 disable requires password + OTP, revokes other sessions, then re-enables", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "security mutation runs once");
  const ownerPhone = "94711234567";

  // Create a second session first so the disable confirmation can prove that
  // every session except the browser performing the change is revoked.
  const otherSession = await createSession(page);
  await login(page);
  await gotoSettings(page);

  await page.getByTestId("twofa-toggle").click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /continue to verification/i })
    .click();

  await page
    .getByLabel("Current password", { exact: true })
    .fill("not-the-owner-password");
  const rejectedPassword = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/settings/security/2fa/start") &&
      response.request().method() === "POST",
  );
  await page.getByTestId("twofa-send-code").click();
  expect((await rejectedPassword).status()).toBe(401);
  await expect(page.getByRole("alert")).toContainText(/invalid|password/i);
  await expect(page.getByTestId("twofa-state")).toContainText(/on/i);

  await page
    .getByLabel("Current password", { exact: true })
    .fill(OWNER_PASSWORD);
  const disableStart = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/settings/security/2fa/start") &&
      response.request().method() === "POST",
  );
  await page.getByTestId("twofa-send-code").click();
  const disableResponse = await disableStart;
  expect(disableResponse.ok()).toBeTruthy();
  const { challenge_id: disableChallenge } = (await disableResponse.json()) as {
    challenge_id: number;
  };
  const disableCode = await latestOtpForChallenge(page, disableChallenge);

  await page.getByLabel("Verification code").fill(differentOtp(disableCode));
  const rejectedCode = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/settings/security/2fa/confirm") &&
      response.request().method() === "POST",
  );
  await page.getByTestId("twofa-confirm").click();
  expect((await rejectedCode).status()).toBe(401);
  await expect(page.getByRole("alert")).toContainText(/incorrect/i);
  await expect(page.getByTestId("twofa-state")).toContainText(/on/i);

  await page.getByLabel("Verification code").fill(disableCode);
  await page.getByTestId("twofa-confirm").click();
  await expect(page.getByTestId("twofa-result")).toContainText(/disabled/i);
  await expect(page.getByTestId("twofa-state")).toContainText(/off/i);
  expect(
    (
      await page.request.get("/api/auth/me", {
        headers: { Authorization: `Bearer ${otherSession.access_token}` },
      })
    ).status(),
  ).toBe(401);

  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("button", { name: /sign out/i }).click();
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password", { exact: true }).fill(OWNER_PASSWORD);
  const directLogin = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/auth/login") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /continue/i }).click();
  const directResponse = await directLogin;
  expect(directResponse.ok()).toBeTruthy();
  expect(((await directResponse.json()) as { mode: string }).mode).toBe(
    "tokens",
  );
  await expect(page.getByTestId("environment-badge")).toBeVisible();

  await gotoSettings(page);
  await page.getByTestId("twofa-toggle").click();
  await page
    .getByLabel("Current password", { exact: true })
    .fill(OWNER_PASSWORD);
  await page.getByLabel("New mobile number").fill(ownerPhone);
  const enableStart = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/settings/security/2fa/start") &&
      response.request().method() === "POST",
  );
  await page.getByTestId("twofa-send-code").click();
  const enableResponse = await enableStart;
  expect(enableResponse.ok()).toBeTruthy();
  const { challenge_id: enableChallenge } = (await enableResponse.json()) as {
    challenge_id: number;
  };
  await page
    .getByLabel("Verification code")
    .fill(await latestOtpForChallenge(page, enableChallenge));
  await page.getByTestId("twofa-confirm").click();
  await expect(page.getByTestId("twofa-result")).toContainText(/enabled/i);
  await expect(page.getByTestId("twofa-state")).toContainText(/on/i);
});
