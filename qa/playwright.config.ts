import { defineConfig, devices } from "@playwright/test";

/**
 * CryptoPilot E2E config. BASE_URL points at the Caddy-served stack.
 * Stage suites live in e2e/ (one file per stage). See docs/qa/QA_STRATEGY.md.
 */
const BASE_URL = process.env.CP_BASE_URL ?? "http://localhost:8090";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 5"] } },
  ],
});
