import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    env: {
      VITE_OIDC_AUTHORITY: "http://idp.test/realms/x",
      VITE_OIDC_CLIENT_ID: "nd-web",
      VITE_API_BASE_URL: "http://api.test",
    },
    coverage: {
      provider: "v8",
      include: ["src/**"],
      exclude: ["src/main.tsx", "src/**/*.test.*"],
      thresholds: { lines: 90, branches: 90 },
    },
  },
});
