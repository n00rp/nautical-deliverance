import { defineConfig } from "@playwright/test";

// B6-R08: the full purchase flow against a running stack (compose in CI, the pilot after a deploy).
// Variables are listed in e2e/flow.spec.ts. Run: pnpm run test:e2e
export default defineConfig({
  testDir: "e2e",
  outputDir: "test-results/e2e",
  reporter: [["list"]],
  // One long flow with shared state: never retried (a retry would create a second E2E inquiry).
  retries: 0,
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: process.env.ND_E2E_BASE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
  },
});
