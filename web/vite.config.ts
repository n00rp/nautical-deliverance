import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    include: ["src/**/*.test.{ts,tsx}"],
    environment: "jsdom",
    env: {
      VITE_OIDC_AUTHORITY: "http://idp.test/realms/x",
      VITE_OIDC_CLIENT_ID: "nd-web",
      VITE_API_BASE_URL: "http://api.test",
    },
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/main.tsx", "src/**/*.test.*", "src/**/*.stories.tsx"],
      thresholds: { lines: 90, branches: 90 },
    },
  },
});
