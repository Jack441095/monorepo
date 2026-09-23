import { defineConfig } from '@playwright/test'

// UI-path tests against a KENN companion running the fake Live backend.
// Uses the installed Google Chrome (channel: 'chrome'); no browser download.
const port = Number(process.env.KENN_E2E_PORT || 8091)

export default defineConfig({
  testDir: './e2e',
  testMatch: /.*\.e2e\.ts$/,
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    channel: 'chrome',
    headless: true,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `python3 ../../tooling/scripts/run_fake_live_companion.py --port ${port}`,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: true,
    timeout: 60_000,
  },
})
