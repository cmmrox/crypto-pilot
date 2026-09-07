import { expect, test } from "@playwright/test";
import { loginThroughUi } from "./helpers/auth";

const dataset = process.env.CP_LAB_DATASET_ID;

test.describe("Experiment Lab real-service acceptance", () => {
  test.skip(!dataset, "Requires the opt-in Lab QA stack and a verified dataset ID");

  test("EL-01 one click runs a baseline, learning cycle and exact reproduction", async ({ page }) => {
    test.setTimeout(180_000);
    await loginThroughUi(page);
    await page.goto("/experiment-lab");
    await page.getByRole("button", { name: "New study", exact: true }).click();
    await page.getByLabel("Study name", { exact: true }).fill(`Acceptance ${test.info().project.name} ${Date.now()}`);
    await page.getByLabel("Binance dataset ID").fill(dataset!);
    await page.getByLabel("Start date (UTC)", { exact: true }).fill("2026-08-01");
    await page.getByLabel("End date (UTC, exclusive)").fill("2026-09-01");
    await page.getByRole("button", { name: "Create study", exact: true }).click();
    await page.getByRole("button", { name: "Run baseline", exact: true }).click();
    await expect(page.getByRole("button", { name: "Iteration in progress" })).toBeDisabled();
    await page.reload();
    await expect(page.locator(".lab-iteration")).toHaveCount(1);
    await expect(page.locator(".lab-iteration > summary")).toContainText("COMPLETED", { timeout: 90_000 });
    await page.getByRole("button", { name: "Run next iteration", exact: true }).click();
    await expect(page.locator(".lab-iteration")).toHaveCount(2);
    await expect(page.locator(".lab-iteration > summary").first()).toContainText("COMPLETED", { timeout: 90_000 });
    await page.locator(".lab-iteration > summary").first().click();
    await page.getByRole("button", { name: "View equity curve", exact: true }).first().click();
    await expect(page.getByRole("figure", { name: "Historical equity curve including initial capital" })).toBeVisible();
    await expect(page.getByText("QA fixture: compare a small stop-distance change.", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "View learned skill", exact: true }).click();
    await expect(page.locator(".lab-skill")).toContainText("Revision 2");
    await page.getByRole("button", { name: "Reproduce exact inputs", exact: true }).first().click();
    await expect(page.locator(".lab-iteration")).toHaveCount(3);
    await expect(page.locator(".lab-iteration > summary").first()).toContainText("COMPLETED", { timeout: 90_000 });
    const summaries = await page.locator(".lab-iteration > summary").allTextContents();
    expect(summaries[0].replace("#3", "")).toBe(summaries[1].replace("#2", ""));
    await expect(page.getByText("None verified", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});

test("EL-02 history paging keeps totals and returns to the latest attempts", async ({ page }) => {
  test.skip(!dataset, "Requires the opt-in Lab QA stack and a verified dataset ID");
  const { createSession } = await import("./helpers/auth");
  const tokens = await createSession(page);
  const headers = { Authorization: `Bearer ${tokens.access_token}` };
  const response = await page.request.post('/api/experiment-lab/studies', { headers, data: {
    name: `Paging ${test.info().project.name} ${Date.now()}`, dataset_id: dataset,
    start: '2026-08-01T00:00:00Z', end: '2026-09-01T00:00:00Z',
  }});
  expect(response.status()).toBe(201);
  const study = await response.json();
  for (let index=0; index<21; index++) {
    const run = await page.request.post(`/api/experiment-lab/studies/${study.id}/iterations`, {
      headers: { ...headers, 'Idempotency-Key': `page-fixture-${index}` }, data: {mode:'ADVISED'},
    });
    expect(run.status()).toBe(202);
    const body = await run.json();
    const cancelled = await page.request.post(`/api/experiment-lab/iterations/${body.id}/cancel`, {headers});
    expect(cancelled.status()).toBe(204);
  }
  await page.goto('/');
  await page.evaluate(({tokens, id}) => {
    sessionStorage.setItem('cp_access', tokens.access_token);
    sessionStorage.setItem('cp_refresh', tokens.refresh_token);
    sessionStorage.setItem('cp-lab-study', id);
  }, {tokens, id: study.id});
  await page.goto('/experiment-lab');
  await expect(page.locator('.lab-iteration')).toHaveCount(20);
  await expect(page.getByText('21 total attempts')).toBeVisible();
  await page.getByRole('button', {name: 'Older iterations', exact:true}).click();
  await expect(page.locator('.lab-iteration')).toHaveCount(1);
  await expect(page.locator('.lab-iteration > summary')).toContainText('#1');
  await page.getByRole('button', {name: 'Latest iterations', exact:true}).click();
  await expect(page.locator('.lab-iteration')).toHaveCount(20);
  await expect(page.locator('.lab-iteration > summary').first()).toContainText('#21');
});
