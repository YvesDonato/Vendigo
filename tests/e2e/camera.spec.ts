import { test, expect } from "@playwright/test";

test("shop and dashboard have no active camera or robot controls; shop exposes no admin navigation", async ({ page }) => {
  const unwantedRequests: string[] = [];
  page.on("request", (request) => {
    if (/\/api\/(camera|robot\/command)/.test(request.url())) unwantedRequests.push(request.url());
  });
  for (const route of ["/shop", "/shop/robot-001", "/dashboard"]) {
    await page.goto(route);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.locator("video")).toHaveCount(0);
    await expect(page.getByText(/camera|robot controls|motor controls|servo controls/i)).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^(forward|backward|left|right|stop|resume|return to base|unlock compartment)$/i })).toHaveCount(0);
    if (route.startsWith("/shop")) {
      await expect(page.locator('a[href*="dashboard"], a[href*="admin"]')).toHaveCount(0);
      await expect(page.getByText(/Recent Purchases|Revenue|Save Inventory|QR scans/i)).toHaveCount(0);
    }
  }
  expect(unwantedRequests).toEqual([]);
});
