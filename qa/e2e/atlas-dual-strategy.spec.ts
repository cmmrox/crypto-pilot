import { expect, test, type Page } from "@playwright/test";
import { login } from "./helpers/auth";

/**
 * Atlas 7 Dual (atlas_dual_v1_4h) release acceptance.
 * The strategy rules and the chronological bot replay are covered in the backend
 * suites; these checks verify the owner console surfaces the release honestly,
 * selection stays guarded and audited, and the watch panel explains the live state.
 * The specs adapt to a stopped or already-running stack so they are safe to run
 * against a live DEMO bot.
 */
const dual = "atlas_dual_v1_4h";
const original = "trend_rider_v6_4h";

async function token(page: Page): Promise<string> {
  const value = await page.evaluate(() => sessionStorage.getItem("cp_access"));
  expect(value).toBeTruthy();
  return value!;
}

async function botStatus(page: Page): Promise<{
  status: string;
  strategy: string;
  environment: string;
}> {
  const response = await page.request.get("/api/bot/status", {
    headers: { Authorization: `Bearer ${await token(page)}` },
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

test("AD-01 library lists the release with its pinned risk profile", async ({
  page,
}) => {
  await login(page);
  await page.goto("/settings");
  const card = page.getByTestId(`strategy-${dual}`);
  await expect(card).toContainText("Atlas 7 Dual · 4h");
  await expect(card).toContainText("LONG + SHORT");
  await card.getByText("How this strategy works", { exact: true }).click();
  const parameters = page.getByTestId(`parameters-${dual}`);
  await expect(parameters).toContainText("stop atr: 2.5");
  await expect(parameters).toContainText("trail atr: 3");
  await expect(parameters).toContainText("risk pct: 4");
  await expect(parameters).toContainText("monthly loss cap: 0.08");
  // Honest caveats ship in the manifest, not marketing copy.
  await expect(card).toContainText("not every month");
  // Parameters are read-only in the console.
  await expect(card.locator("input")).toHaveCount(0);
});

test("AD-02 API exposes the manifest, risk caps and direction", async ({
  page,
}) => {
  await login(page);
  const response = await page.request.get("/api/strategies", {
    headers: { Authorization: `Bearer ${await token(page)}` },
  });
  expect(response.ok()).toBeTruthy();
  const rows = (await response.json()) as Array<{
    name: string;
    display_name: string;
    direction: string;
    params: Record<string, number>;
  }>;
  const release = rows.find((row) => row.name === dual);
  expect(release, "Atlas 7 Dual must be registered").toBeTruthy();
  expect(release!.display_name).toBe("Atlas 7 Dual · 4h");
  expect(release!.direction).toBe("LONG + SHORT");
  expect(release!.params.risk_pct).toBe(4);
  expect(release!.params.monthly_loss_cap).toBe(0.08);
  expect(release!.params.stop_atr).toBe(2.5);
});

test("AD-03 switching is refused while the bot runs, and audited when stopped", async ({
  page,
}) => {
  await login(page);
  const before = await botStatus(page);
  const headers = { Authorization: `Bearer ${await token(page)}` };

  if (before.status !== "stopped") {
    // Guard: a running bot may never have its strategy swapped underneath it.
    const refused = await page.request.put("/api/settings/strategy", {
      headers,
      data: { name: before.strategy === dual ? original : dual },
    });
    expect(refused.status()).toBe(409);
    await page.goto("/settings");
    const active = page.getByTestId(`strategy-${before.strategy}`);
    await expect(active.getByText("Active", { exact: true })).toBeVisible();
    return;
  }

  await page.goto("/settings");
  const card = page.getByTestId(`strategy-${dual}`);
  await page.getByTestId(`select-${dual}`).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("does not start trading");
  await dialog
    .getByRole("button", { name: "Select release", exact: true })
    .click();
  try {
    await expect(card.getByText("Active", { exact: true })).toBeVisible();
    const status = await botStatus(page);
    expect(status.status).toBe("stopped");
    const events = await page.request.get("/api/events?category=strategy", {
      headers,
    });
    expect(
      (await events.json()).items.some(
        (event: { payload_json: { to?: string } }) =>
          event.payload_json?.to === dual,
      ),
      "strategy switch must be audited",
    ).toBeTruthy();
  } finally {
    await page.getByTestId(`select-${before.strategy}`).click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Select release", exact: true })
      .click();
    await expect(
      page
        .getByTestId(`strategy-${before.strategy}`)
        .getByText("Active", { exact: true }),
    ).toBeVisible();
  }
});

test("AD-04 the watch panel explains the active release without predicting a trade", async ({
  page,
}) => {
  await login(page);
  const status = await botStatus(page);
  await page.goto("/overview");
  const panel = page.getByTestId("strategy-watch-panel");
  await expect(panel).toBeVisible();
  if (status.strategy === dual) {
    await expect(panel).toContainText("Atlas 7 Dual · 4h");
    await expect(panel).toContainText("Regime");
    await expect(panel).toContainText("Pullback entry");
    await expect(panel).toContainText("Squeeze breakout");
  }
  await expect(panel).toContainText("not a guaranteed trade or execution price");
});
