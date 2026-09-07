import { expect, type Page } from "@playwright/test";

export const OWNER_EMAIL = process.env.CP_QA_OWNER_EMAIL ?? "owner@cryptopilot.app";
export const OWNER_PASSWORD = process.env.CP_QA_OWNER_PASSWORD ?? "PilotOwner!2026";

interface Tokens {
  access_token: string;
  refresh_token: string;
}

/**
 * Complete the password step. The E2E stack must run with
 * CP_ENVIRONMENT=test + CP_OTP_TEST_MODE=true so its fake SMS delivery can be
 * read through the test-only endpoint. Production rejects that configuration.
 */
export async function passwordStep(page: Page): Promise<string> {
  await page.goto("/");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password", { exact: true }).fill(OWNER_PASSWORD);
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/auth/login") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /continue/i }).click();
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { otp_token: string | null };
  expect(body.otp_token).not.toBeNull();
  return body.otp_token!;
}

export async function latestOtp(page: Page, otpToken: string): Promise<string> {
  const response = await page.request.get("/api/auth/otp/dev-code", {
    headers: { Authorization: `Bearer ${otpToken}` },
  });
  expect(
    response.ok(),
    "test SMS code endpoint must be available in the E2E stack",
  ).toBeTruthy();
  const body = (await response.json()) as { code: string };
  return body.code;
}

export async function latestOtpForChallenge(
  page: Page,
  challengeId: number,
): Promise<string> {
  const response = await page.request.get(
    `/api/auth/otp/dev-code?challenge_id=${challengeId}`,
  );
  expect(
    response.ok(),
    "test SMS code must exist for the requested phone",
  ).toBeTruthy();
  const body = (await response.json()) as { code: string };
  return body.code;
}

/** Return a valid-looking OTP that is guaranteed to differ from `code`. */
export function differentOtp(code: string): string {
  return code === "000000" ? "000001" : "000000";
}

export async function loginThroughUi(page: Page): Promise<void> {
  const otpToken = await passwordStep(page);
  await expect(
    page.getByRole("heading", { name: /6-digit code/i }),
  ).toBeVisible();
  await page
    .getByLabel("Authentication code")
    .fill(await latestOtp(page, otpToken));
  await page.getByRole("button", { name: /verify & enter/i }).click();
  await expect(page.getByTestId("environment-badge")).toBeVisible();
}

export async function createSession(page: Page): Promise<Tokens> {
  const password = await page.request.post("/api/auth/login", {
    data: { email: OWNER_EMAIL, password: OWNER_PASSWORD },
  });
  expect(password.ok()).toBeTruthy();
  const pending = (await password.json()) as {
    mode: "tokens" | "otp";
    access_token: string | null;
    refresh_token: string | null;
    otp_token: string | null;
  };
  if (
    pending.mode === "tokens" &&
    pending.access_token &&
    pending.refresh_token
  ) {
    return {
      access_token: pending.access_token,
      refresh_token: pending.refresh_token,
    };
  }
  expect(pending.otp_token).not.toBeNull();
  const verification = await page.request.post("/api/auth/otp/verify", {
    data: { code: await latestOtp(page, pending.otp_token!) },
    headers: { Authorization: `Bearer ${pending.otp_token}` },
  });
  expect(verification.ok()).toBeTruthy();
  return (await verification.json()) as Tokens;
}

async function installSession(page: Page, tokens: Tokens): Promise<void> {
  await page.goto("/");
  await page.evaluate((value: Tokens) => {
    sessionStorage.setItem("cp_access", value.access_token);
    sessionStorage.setItem("cp_refresh", value.refresh_token);
  }, tokens);
  await page.reload();
}

/** Create an isolated authenticated session for each test. */
export async function login(page: Page): Promise<void> {
  const tokens = await createSession(page);
  await installSession(page, tokens);
  const environmentBadge = page.getByTestId("environment-badge");
  await expect(environmentBadge).toBeVisible({ timeout: 15_000 });
}
