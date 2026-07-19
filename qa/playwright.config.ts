import { defineConfig, devices } from "@playwright/test";

/**
 * CryptoPilot E2E config. BASE_URL points at the Caddy-served stack.
 * Stage suites live in e2e/ (one file per stage). See docs/qa/QA_STRATEGY.md.
 */
const BASE_URL = process.env.CP_BASE_URL ?? "http://localhost:8090";

export default defineConfig({
  testDir: "./e2e",
  // This is a single-owner, stateful trading system. Security changes revoke
  // other sessions and lifecycle tests mutate shared bot/settings state, so
  // cross-test parallelism would make the suite nondeterministic.
  fullyParallel: false,
  workers: 1,
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
