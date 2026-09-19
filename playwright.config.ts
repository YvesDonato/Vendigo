import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: "http://127.0.0.1:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    { command: "npm run start -- --hostname 127.0.0.1 --port 3100", url: "http://127.0.0.1:3100/api/state", reuseExistingServer: !process.env.CI, timeout: 60_000, env: { CAMERA_STREAM_URL: "" } },
    { command: "node tests/camera-fixture.mjs", url: "http://127.0.0.1:3102/health", timeout: 20_000 },
    { command: "npm run start -- --hostname 127.0.0.1 --port 3101", url: "http://127.0.0.1:3101/api/state", reuseExistingServer: !process.env.CI, timeout: 60_000, env: { CAMERA_STREAM_URL: "http://127.0.0.1:3102/stream" } },
  ],
});
