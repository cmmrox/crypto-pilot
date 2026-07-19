import { expect, test, type Page } from "@playwright/test";
import { login } from "./helpers/auth";

/**
 * Stage 10 — Reliability engineering (QA-10, UI slice).
 * Verifies the deep-health endpoint and the Operations panel. The chaos drills
 * (restore, restart) are shell scripts under deploy/scripts/drills and are run
 * as part of acceptance, not from the browser.
 */

test("QA-10.01 deep health endpoint reports scheduler + dead-man", async ({
  request,
}) => {
  const resp = await request.get("/health/deep");
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  expect(body).toHaveProperty("scheduler_alive");
  expect(body).toHaveProperty("ingest_overdue");
  expect(body.ingest_overdue).toBe(false);
});

test("QA-10.02 Operations panel shows health", async ({ page }) => {
  await login(page);
  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: /settings/i }).click();
  await expect(page.getByTestId("operations-card")).toBeVisible();
  await expect(page.getByTestId("ops-status")).toBeVisible();
  await page.getByTestId("ops-refresh").click();
  await expect(page.getByTestId("operations-card")).toContainText(/scheduler/i);
});
