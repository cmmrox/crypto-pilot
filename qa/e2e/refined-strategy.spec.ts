import { expect, test } from "@playwright/test";
import { login } from "./helpers/auth";

const refined = "trend_rider_refined_v1_4h";
const original = "trend_rider_v6_4h";

test("REF-01 select pinned refined release, retain DEMO and stopped state, restore original", async ({
  page,
}) => {
  await login(page);
  await page.goto("/settings");
  await expect(page.getByTestId("active-env")).toContainText("DEMO");
  const card = page.getByTestId(`strategy-${refined}`);
  await expect(card).toContainText("Atlas 6 Trail · 4h");
  await card.getByText("How this strategy works", { exact: true }).click();
  await expect(page.getByTestId(`parameters-${refined}`)).toContainText(
    "trail atr: 4.5",
  );
  await expect(card).toContainText("worse final-year loss");
  await expect(card.locator("input")).toHaveCount(0);

  await page.getByTestId(`select-${refined}`).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("does not start trading");
  await expect(dialog).toContainText("15% long risk");
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByTestId(`select-${refined}`)).toBeVisible();

  await page.getByTestId(`select-${refined}`).click();
  await dialog
    .getByRole("button", { name: "Select release", exact: true })
    .click();
  try {
    await expect(card.getByText("Active", { exact: true })).toBeVisible();
    await page.reload();
    await expect(card.getByText("Active", { exact: true })).toBeVisible();
    await expect(page.getByTestId("active-env")).toContainText("DEMO");
    const token = await page.evaluate(() =>
      sessionStorage.getItem("cp_access"),
    );
    const headers = { Authorization: `Bearer ${token}` };
    const status = await page.request.get("/api/bot/status", { headers });
    expect(status.ok()).toBeTruthy();
    expect((await status.json()).status).toBe("stopped");
    const events = await page.request.get("/api/events?category=strategy", {
      headers,
    });
    expect(
      (await events.json()).items.some(
        (event: { payload_json: { to?: string } }) =>
          event.payload_json?.to === refined,
      ),
    ).toBeTruthy();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.goto("/overview");
    await expect(page.getByTestId("strategy-watch-panel")).toContainText(
      "Atlas 6 Trail · 4h",
    );
    await page.goto("/settings");
  } finally {
    await page.getByTestId(`select-${original}`).click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Select release", exact: true })
      .click();
    await expect(
      page
        .getByTestId(`strategy-${original}`)
        .getByText("Active", { exact: true }),
    ).toBeVisible();
  }
});
