import { expect, test } from "@playwright/test";
import { login } from "./helpers/auth";

// Browser contract regression only: LIVE responses are simulated locally.
// These tests never switch an exchange account or start a bot.
test("ENV-01 header and Settings reflect LIVE on load and reload", async ({
  page,
}, testInfo) => {
  await page.route("**/api/bot/status", (route) =>
    route.fulfill({
      json: {
        status: "running",
        environment: "LIVE",
        strategy: "trend_rider_v6_4h",
        run_id: 1,
        started_at: null,
        safe_mode_reason: null,
      },
    }),
  );
  await login(page);
  await page.goto("/settings");
  await expect(page.getByTestId("active-env")).toHaveText("LIVE active");
  await expect(page.getByTestId("environment-badge")).toContainText("LIVE");
  await expect(page.getByTestId("environment-badge")).toHaveClass(/live/);
  await expect(page.getByTestId("environment-badge")).toContainText(
    "Real funds",
  );
  await page.reload();
  await expect(page.getByTestId("environment-badge")).toContainText("LIVE");
  await page.screenshot({
    path: testInfo.outputPath("live-environment.png"),
    fullPage: true,
  });
});

test("ENV-02 confirmed environment changes update both surfaces", async ({
  page,
}) => {
  let environment = "DEMO";
  await page.route("**/api/bot/status", (route) =>
    route.fulfill({
      json: {
        status: "stopped",
        environment,
        strategy: "trend_rider_v6_4h",
        run_id: null,
        started_at: null,
        safe_mode_reason: null,
      },
    }),
  );
  await page.route("**/api/settings/environment", async (route) => {
    environment = route.request().postDataJSON().environment;
    await route.fulfill({ json: { message: "changed" } });
  });
  await login(page);
  await page.goto("/settings");
  await expect(page.getByTestId("active-env")).toHaveText("DEMO active");
  await page.getByTestId("env-live").click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox").fill("LIVE");
  await dialog
    .getByRole("button", { name: "Switch to LIVE", exact: true })
    .click();
  await expect(page.getByTestId("active-env")).toHaveText("LIVE active");
  await expect(page.getByTestId("environment-badge")).toContainText("LIVE");
  await page.getByTestId("env-demo").click();
  await dialog
    .getByRole("button", { name: "Switch to DEMO", exact: true })
    .click();
  await expect(page.getByTestId("environment-badge")).toContainText("DEMO");
  await expect(page.getByTestId("active-env")).toHaveText("DEMO active");
});

test("ENV-03 unknown environment never defaults to DEMO", async ({ page }) => {
  await page.route("**/api/bot/status", (route) =>
    route.fulfill({ status: 503, json: { detail: "unavailable" } }),
  );
  await login(page);
  await page.goto("/settings");
  await expect(page.getByTestId("environment-badge")).toContainText(
    "Unavailable",
  );
  await expect(page.getByTestId("active-env")).toContainText("Unavailable");
  await expect(page.getByTestId("env-live")).toBeDisabled();
  await expect(page.getByTestId("env-demo")).toBeDisabled();
});

test("ENV-04 rejected switch retains confirmed environment", async ({
  page,
}) => {
  await page.route("**/api/bot/status", (route) =>
    route.fulfill({
      json: {
        status: "stopped",
        environment: "DEMO",
        strategy: "trend_rider_v6_4h",
        run_id: null,
        started_at: null,
        safe_mode_reason: null,
      },
    }),
  );
  await page.route("**/api/settings/environment", (route) =>
    route.fulfill({ status: 409, json: { detail: "Switch blocked" } }),
  );
  await login(page);
  await page.goto("/settings");
  await page.getByTestId("env-live").click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox").fill("LIVE");
  await dialog
    .getByRole("button", { name: "Switch to LIVE", exact: true })
    .click();
  await expect(dialog).toContainText("Switch blocked");
  await expect(page.getByTestId("active-env")).toHaveText("DEMO active");
  await expect(page.getByTestId("environment-badge")).toContainText("DEMO");
});

test("ENV-05 focus refresh clears stale LIVE and recovers consistently", async ({
  page,
}) => {
  let available = true;
  await page.route("**/api/bot/status", (route) =>
    available
      ? route.fulfill({
          json: {
            status: "stopped",
            environment: "LIVE",
            strategy: "trend_rider_v6_4h",
            run_id: null,
            started_at: null,
            safe_mode_reason: null,
          },
        })
      : route.fulfill({ status: 503, json: { detail: "unavailable" } }),
  );
  await login(page);
  await page.goto("/settings");
  await expect(page.getByTestId("environment-badge")).toContainText("LIVE");
  available = false;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByTestId("environment-badge")).toContainText(
    "Unavailable",
  );
  await expect(page.getByTestId("env-demo")).toBeDisabled();
  available = true;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByTestId("environment-badge")).toContainText("LIVE");
  await expect(page.getByTestId("active-env")).toHaveText("LIVE active");
});
