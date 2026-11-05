import { defineConfig } from "@playwright/test";

// Baselines are Linux-only: generate them in the pinned Playwright image (npm run test:visual:docker).
export default defineConfig({
  testDir: "tests/visual",
  snapshotPathTemplate: "{testDir}/__screenshots__/{arg}{ext}",
  outputDir: "test-results",
  reporter: [["list"]],
  expect: {
    // Story root only. Per-pixel colour tolerance 0.1 absorbs anti-aliasing; at most 20 pixels may differ.
    toHaveScreenshot: { maxDiffPixels: 20, threshold: 0.1, animations: "disabled" },
  },
  use: { baseURL: "http://127.0.0.1:6006" },
  webServer: {
    command:
      "pnpm exec vite preview --host 127.0.0.1 --port 6006 --strictPort --outDir storybook-static",
    url: "http://127.0.0.1:6006/index.json",
    reuseExistingServer: false,
  },
});
