import { defineConfig } from "@playwright/test";

// B6-R08: the full purchase flow against a running stack (compose in CI, the pilot after a deploy).
// Variables are listed in e2e/flow.spec.ts. Run: pnpm run test:e2e
const baseURL = process.env.ND_E2E_BASE_URL ?? "http://localhost:8080";
const LOCAL_HOSTS = ["localhost", "127.0.0.1"];

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
    baseURL,
    // A trace records typed passwords and bearer tokens. Local and CI runs use throwaway dev
    // credentials and keep it; a remote (pilot) run uses real ones, so nothing is recorded.
    trace: LOCAL_HOSTS.includes(new URL(baseURL).hostname) ? "retain-on-failure" : "off",
  },
});
