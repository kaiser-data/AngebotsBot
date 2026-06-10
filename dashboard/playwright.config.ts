import { defineConfig } from "@playwright/test";

/**
 * E2E acceptance tests for the persona use cases (see PERSONAS.md).
 * Runs against the dev server + the real Supabase project, so assertions
 * are written to be data-tolerant (counts, not exact values).
 */
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: true,
  retries: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
