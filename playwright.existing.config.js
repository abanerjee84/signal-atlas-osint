import { defineConfig } from "@playwright/test";

// This verification never starts, stops or replaces application servers.
export default defineConfig({
  testDir: "./tests/browser",
  testMatch: ["cyber-observations.spec.js", "infrastructure-layer.spec.js"],
  workers: 1,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:5173",
    headless: true,
    viewport: { width: 1440, height: 960 },
  },
  reporter: "list",
});
