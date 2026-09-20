import { test, expect } from "@playwright/test";
import type { AppSnapshot } from "../../src/types";

test("mobile purchase relocks and immediately updates a separate dashboard session", async ({ browser, request }) => {
  const customer = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const operator = await browser.newContext({ viewport: { width: 1440, height: 1050 } });
  const shop = await customer.newPage();
  const dashboard = await operator.newPage();
  const errors: string[] = [];
  shop.on("pageerror", (error) => errors.push(error.message));
  dashboard.on("pageerror", (error) => errors.push(error.message));
  await dashboard.goto("/dashboard");
  await expect(dashboard.getByRole("heading", { name: "Dashboard", exact: true })).toBeVisible();
  const before: AppSnapshot = await (await request.get("/api/state")).json();
  await shop.goto("/shop");
  await expect(shop.getByRole("heading", { name: "Snacks & treats." })).toBeVisible();
  await expect(shop.locator(".product-card h2")).toHaveText(["Rice Krispies Treats Original", "KitKat", "Hello Panda Chocolate", "Kirkland Soft & Chewy Granola Bar", "Biscoff Cookies", "Smarties", "Brookside Acai & Blueberry Dark Chocolate"]);
  for (const product of before.products) {
    expect(product.priceCents).toBe(100);
    await expect(shop.getByTestId(`product-${product.id}`).getByText("$1.00", { exact: true })).toBeVisible();
  }
  await expect(dashboard.getByTestId("kpi-scans")).toHaveText(String(before.qrScans + 1));
  await shop.screenshot({ path: "test-results/storefront-mobile.png", fullPage: true });
  await dashboard.screenshot({ path: "test-results/dashboard-desktop.png", fullPage: true });
  expect(await shop.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expect(shop.getByTestId("product-rice-krispies-original").getByRole("button", { name: "Get Item" })).toBeInViewport({ ratio: 1 });
  expect(await dashboard.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await shop.getByTestId("product-rice-krispies-original").getByRole("button", { name: "Get Item" }).click();
  await expect(shop.getByRole("dialog")).toBeVisible();
  await expect(shop.getByRole("dialog").getByText("$1.00", { exact: true })).toBeVisible();
  await shop.getByRole("button", { name: "Confirm" }).click();
  await expect(shop.getByRole("heading", { name: "Compartment unlocked" })).toBeVisible();
  await expect(shop.getByText("Take your Rice Krispies Treats Original", { exact: true })).toBeVisible();
  await shop.screenshot({ path: "test-results/purchase-unlocked-mobile.png", fullPage: true });
  const during: AppSnapshot = await (await request.get("/api/state")).json();
  expect(during.inventory[0].stock).toBe(before.inventory[0].stock);

  // Recover the open compartment after a full page reload.
  await shop.reload();
  await expect(dashboard.getByTestId("kpi-scans")).toHaveText(String(before.qrScans + 1));
  await expect(shop.getByRole("heading", { name: "Compartment unlocked" })).toBeVisible();
  await expect(shop.getByRole("dialog")).toBeHidden({ timeout: 16_000 });
  await expect(shop.getByText("Pickup complete. Enjoy!")).toBeVisible();
  await expect(dashboard.getByTestId("kpi-units")).toHaveText(String(before.transactions.length + 1));
  const after: AppSnapshot = await (await request.get("/api/state")).json();
  const revenue = before.transactions.reduce((sum, sale) => sum + sale.amountCents, 0);
  expect(after.transactions[0].amountCents).toBe(100);
  await expect(dashboard.getByTestId("kpi-revenue")).toHaveText(`$${((revenue + 100) / 100).toFixed(2)}`);
  await expect(dashboard.getByTestId(`sale-${after.transactions[0].id}`)).toContainText("Rice Krispies Treats Original");
  await expect(dashboard.getByTestId(`sale-${after.transactions[0].id}`)).toContainText("$1.00");
  await expect(dashboard.getByTestId("kpi-conversion")).toHaveText(`${(after.transactions.length / after.qrScans * 100).toFixed(1)}%`);
  expect(after.inventory[0].stock).toBe(before.inventory[0].stock - 1);
  await expect(shop.getByTestId("product-rice-krispies-original")).toContainText(`${after.inventory[0].stock} left`);
  expect(errors).toEqual([]);
  await customer.close(); await operator.close();
});

test("manual inventory editing persists and updates an open shop; sold-out purchases are rejected", async ({ page, request }) => {
  await page.goto("/dashboard");
  const shop = await page.context().newPage();
  await shop.goto("/shop");
  await expect(page.getByLabel("Rice Krispies Treats Original", { exact: true })).toBeVisible();
  await page.getByLabel("Rice Krispies Treats Original", { exact: true }).fill("5");
  await page.getByRole("button", { name: "Save Inventory", exact: true }).click();
  await expect(page.getByText("Inventory saved.")).toBeVisible();
  await expect(shop.getByTestId("product-rice-krispies-original")).toContainText("5 left");
  await page.reload();
  await expect(page.getByLabel("Rice Krispies Treats Original", { exact: true })).toHaveValue("5");
  await page.getByLabel("Rice Krispies Treats Original", { exact: true }).fill("0");
  await page.getByRole("button", { name: "Save Inventory", exact: true }).click();
  await expect(shop.getByTestId("product-rice-krispies-original").getByRole("button")).toBeDisabled();
  await expect(shop.getByTestId("product-rice-krispies-original")).toContainText("Sold out");
  const denied = await request.post("/api/purchases", { data: { orderId: "sold-out-api", robotId: "robot-001", productId: "rice-krispies-original", compartmentId: 1, sessionId: "sold-out-test" } });
  expect(denied.status()).toBe(409);
  const invalid = await request.post("/api/inventory", { data: { robotId: "robot-001", items: [{ productId: "rice-krispies-original", stock: -1 }] } });
  expect(invalid.status()).toBe(400);
  await page.getByLabel("Rice Krispies Treats Original", { exact: true }).fill("5");
  await page.getByRole("button", { name: "Save Inventory", exact: true }).click();
  await expect(shop.getByTestId("product-rice-krispies-original")).toContainText("5 left");
});

test("snack catalog, accessible confirmation, QR generation, and narrow layouts work", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/shop");
  await expect(page.getByRole("button", { name: "Drinks", exact: true })).toHaveCount(0);
  await expect(page.getByTestId("product-kitkat")).toBeVisible();
  await expect(page.getByTestId("product-kirkland-granola-bar")).toBeVisible();
  await expect(page.getByTestId("product-brookside-acai-blueberry")).toBeVisible();
  await page.getByTestId("product-kitkat").getByRole("button").click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByTestId("product-kitkat").getByRole("button")).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Shop QR" }).click();
  const qr = page.getByRole("dialog");
  await expect(qr.getByRole("img", { name: /QR code for/ })).toBeVisible();
  await expect(qr.getByRole("link", { name: "Download QR" })).toHaveAttribute("href", /^data:image\/png;base64,/);
  await qr.getByRole("button", { name: "Close dialog" }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/dashboard-mobile.png", fullPage: true });
});

test("API rejects malformed requests and unknown robots", async ({ request, page }) => {
  const invalidJson = await request.post("/api/robot/unlock", { data: "{", headers: { "Content-Type": "application/json" } });
  expect(invalidJson.status()).toBe(400);
  const invalidCompartment = await request.post("/api/robot/unlock", { data: { orderId: "api-test", robotId: "robot-001", productId: "rice-krispies-original", compartmentId: 99, sessionId: "api-test" } });
  expect(invalidCompartment.status()).toBe(400);
  const invalidCommand = await request.post("/api/robot/command", { data: { robotId: "robot-001", command: "fly" } });
  expect(invalidCommand.status()).toBe(400);
  const camera = await request.get("/api/camera/stream");
  expect(camera.status()).toBe(503);
  const missing = await page.goto("/shop/robot-missing");
  expect(missing?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "Storefront not found" })).toBeVisible();

});

test("a disconnected customer does not interrupt the server's pickup timer", async ({ browser, request }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/shop");
  const before: AppSnapshot = await (await request.get("/api/state")).json();
  await page.getByTestId("product-biscoff-cookies").getByRole("button").click();
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByRole("heading", { name: "Compartment unlocked" })).toBeVisible();
  await context.close();
  await expect.poll(async () => {
    const snapshot: AppSnapshot = await (await request.get("/api/state")).json();
    return snapshot.transactions.length;
  }, { timeout: 15_000, intervals: [1000] }).toBe(before.transactions.length + 1);
  const after: AppSnapshot = await (await request.get("/api/state")).json();
  expect(after.activeOrders).toHaveLength(0);
  expect(after.inventory.find((i) => i.productId === "biscoff-cookies")!.stock).toBe(before.inventory.find((i) => i.productId === "biscoff-cookies")!.stock - 1);
});
