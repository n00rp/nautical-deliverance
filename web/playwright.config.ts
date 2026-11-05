import { defineConfig } from "@playwright/test";

// Baselines are Linux-only: generate them in the pinned Playwright image (npm run test:visual:docker).
export default defineConfig({
  testDir: "tests/visual",
  snapshotPathTemplate: "{testDir}/__screenshots__/{arg}{ext}",
  outputDir: "test-results",
  reporter: [["list"]],
  expect: {
    // Tolerates sub-pixel anti-aliasing only: at most 0.1 % of pixels may differ.
    toHaveScreenshot: { maxDiffPixelRatio: 0.001, animations: "disabled" },
  },
  use: { baseURL: "http://127.0.0.1:6006" },
  webServer: {
    command:
      "pnpm exec vite preview --host 127.0.0.1 --port 6006 --strictPort --outDir storybook-static",
    url: "http://127.0.0.1:6006/index.json",
    reuseExistingServer: false,
  },
});
