import { test, expect } from "@playwright/test";

test("preserved MJPEG protocol streams through the proxy and handles an offline camera", async ({ page, request }) => {
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.setContent('<main style="background:#294932;color:#e4eeca;font:28px monospace;width:500px;height:280px;padding:30px">CAMERA INTEGRATION TEST<br><small>MJPEG frame · simulated ESP32</small></main>');
  const jpeg = await page.locator("main").screenshot({ type: "jpeg" });
  await request.post("http://127.0.0.1:3102/frame", { data: jpeg, headers: { "Content-Type": "image/jpeg" } });
  await page.goto("http://127.0.0.1:3101/dashboard");
  const camera = page.getByRole("img", { name: "Live view from Hawk #1’s onboard camera" });
  await expect(camera).toBeVisible();
  await expect(page.getByText("Feed connected", { exact: true })).toBeVisible();
  await expect(page.locator(".robot-vitals").getByText("Online", { exact: true })).toBeVisible();
  expect(await camera.evaluate((image) => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  await page.locator("#camera").screenshot({ path: "test-results/camera-stream-test.png" });
  await request.post("http://127.0.0.1:3102/offline");
  const offline = await request.get("http://127.0.0.1:3101/api/camera/stream");
  expect(offline.status()).toBe(502);
  await page.reload();
  await expect(page.getByText("Waiting for a little perspective")).toBeVisible();
  await expect(page.locator(".robot-vitals").getByText("Offline", { exact: true })).toBeVisible();
  await request.post("http://127.0.0.1:3102/frame", { data: jpeg, headers: { "Content-Type": "image/jpeg" } });
  await page.getByRole("button", { name: "Reconnect camera" }).click();
  await expect(page.getByText("Feed connected", { exact: true })).toBeVisible();
});
