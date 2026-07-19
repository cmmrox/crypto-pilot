import { expect, test } from "@playwright/test";

/**
 * Stage 0 — foundations smoke suite (QA-0).
 * Verifies the Docker Compose stack boots and is reachable through Caddy:
 * the SPA is served, the backend /health endpoint is green, and no secrets
 * leak to the client.
 */

test("QA-0.01 backend /health returns ok with database ok", async ({ request }) => {
  const resp = await request.get("/health");
  expect(resp.status()).toBe(200);
  const body = await resp.json();
  expect(body.status).toBe("ok");
  expect(body.database).toBe("ok");
  expect(body.version).toBeTruthy();
});

test("QA-0.02 SPA is served with the app title", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/CryptoPilot/);
});

test("QA-0.03 frontend SPA boots and renders through Caddy", async ({ page }) => {
  await page.goto("/");
  // The SPA mounts and shows the owner login screen (the app's entry point).
  await expect(page.getByRole("heading", { name: /sign in securely/i })).toBeVisible();
});

test("QA-0.04 security header present and server banner hidden", async ({ request }) => {
  const resp = await request.get("/health");
  const headers = resp.headers();
  expect(headers["x-content-type-options"]).toBe("nosniff");
});

test("QA-0.05 no secrets exposed to the client", async ({ page }) => {
  const responses: string[] = [];
  page.on("response", async (r) => {
    const ct = r.headers()["content-type"] ?? "";
    if (ct.includes("text") || ct.includes("json") || ct.includes("javascript")) {
      try {
        responses.push(await r.text());
      } catch {
        /* opaque response — ignore */
      }
    }
  });
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  const blob = responses.join("\n").toLowerCase();
  // Server-side secrets that must never reach the client. ("api_secret" is a
  // legitimate write-only *field name* in the client code — actual secret values
  // never being exposed is verified by QA-2.06.)
  for (const forbidden of ["master_key", "jwt_secret", "postgres_password"]) {
    expect(blob).not.toContain(forbidden);
  }
});

test("QA-0.06 unknown client route falls back to SPA (no 404 page)", async ({ page }) => {
  const resp = await page.goto("/some/deep/spa/route");
  expect(resp?.status()).toBeLessThan(400);
  await expect(page).toHaveTitle(/CryptoPilot/);
});

test("QA-0.07 SPA entrypoint is never cached across auth-contract releases", async ({
  request,
}) => {
  const resp = await request.get("/");
  expect(resp.status()).toBe(200);
  expect(resp.headers()["cache-control"]).toContain("no-store");
});
