import { defineConfig } from "@playwright/test";

// Pure client-library tests: no browser, web server, or live API required.
export default defineConfig({
  testDir: "./tests/unit",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
});
