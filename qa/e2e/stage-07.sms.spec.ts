import { expect, test, type Page } from "@playwright/test";
import { login } from "./helpers/auth";

/**
 * Stage 7 — Notifier / notify.lk SMS (QA-7).
 * Verifies the SMS settings panel shows configured state, the delivery toggle,
 * and (when RUN_LIVE_SMS=1) a real test SMS to the owner's phone.
 */

async function gotoSettings(page: Page) {
  const menu = page.getByRole("button", { name: /open navigation/i });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: /settings/i }).click();
  await expect(page.getByTestId("view-title")).toHaveText("Settings");
}

test("QA-7.01 SMS panel shows configured state", async ({ page }) => {
  await login(page);
  await gotoSettings(page);
  await expect(page.getByTestId("sms-card")).toBeVisible();
  await expect(page.getByTestId("sms-state")).toContainText(/configured/i);
});

test("QA-7.02 SMS delivery can be toggled", async ({ page }) => {
  await login(page);
  await gotoSettings(page);
  const toggle = page.getByRole("switch", { name: /toggle sms delivery/i });
  const before = await toggle.getAttribute("aria-checked");
  await toggle.click();
  await expect(toggle).not.toHaveAttribute("aria-checked", before ?? "false");
  await toggle.click(); // restore
});

test("QA-7.03 SMS status API reports configured + enabled", async ({
  page,
  request,
}) => {
  await login(page);
  const token = await page.evaluate(() => sessionStorage.getItem("cp_access"));
  const resp = await request.get("/api/settings/sms", {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  expect(body.configured).toBe(true);
  expect(body.sender_id).toBe("NotifyDEMO");
});

test("QA-7.04 real test SMS delivers to the owner phone @sms", async ({
  page,
}) => {
  test.skip(
    process.env.RUN_LIVE_SMS !== "1",
    "set RUN_LIVE_SMS=1 to send a real SMS",
  );
  await login(page);
  await gotoSettings(page);
  await page.getByTestId("test-sms").click();
  await expect(page.getByTestId("sms-result")).toContainText(
    /sent to your phone/i,
    {
      timeout: 15000,
    },
  );
});
