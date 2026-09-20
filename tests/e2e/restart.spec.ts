import { test, expect } from "@playwright/test";
import { spawn, type ChildProcess, execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { once } from "node:events";
import type { AppSnapshot } from "../../src/types";

// Actual backend processes, with their own JSON directory; never use the operator's data.
test("backend restart persistence and live file/admin/purchase changes reach shop, dashboard and the same Vendi session", async ({ playwright, browser }) => {
  test.setTimeout(90_000);
  const directory = mkdtempSync(join(tmpdir(), "vendigo-restart-"));
  const baseURL = "http://127.0.0.1:3120";
  const api = await playwright.request.newContext({ baseURL });
  let server: ChildProcess | undefined;
  let logs = "";
  const stop = async () => {
    if (server && server.exitCode === null && server.signalCode === null) {
      const process = server;
      const done = once(process, "exit");
      process.kill("SIGTERM");
      // An open SSE connection can hold Next's graceful shutdown indefinitely.
      // A real process restart must also recover from a forced termination.
      const force = setTimeout(() => process.kill("SIGKILL"), 2_000);
      try { await done; } finally { clearTimeout(force); }
    }
  };
  const start = async () => {
    server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3120"], {
      env: { ...process.env, VENDIGO_DATA_DIR: directory, LID_API_URL: "", LID_API_ONLY: "" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    server.stdout?.on("data", (chunk) => { logs += chunk; });
    server.stderr?.on("data", (chunk) => { logs += chunk; });
    await expect.poll(async () => {
      if (server?.exitCode !== null) throw new Error(logs);
      return api.get("/api/state").then((r) => r.status()).catch(() => 0);
    }, { timeout: 15_000 }).toBe(200);
  };
  const snapshot = async (): Promise<AppSnapshot> => (await api.get("/api/state")).json();
  try {
    await start();
    expect((await api.post("/api/inventory", { data: { robotId: "robot-001", items: [{ productId: "rice-krispies-original", stock: 5 }] } })).ok()).toBe(true);
    for (let i = 0; i < 7; i++) await api.post("/api/scans", { data: { robotId: "robot-001", sessionId: `restart-visit-${i}` } });
    await stop(); await start();
    expect((await snapshot()).inventory[0].stock).toBe(5);
    expect((await snapshot()).qrScans).toBe(7);
    const purchase = { orderId: "restart-purchase", robotId: "robot-001", productId: "rice-krispies-original", compartmentId: 1, sessionId: "restart-visit-0" };
    expect((await api.post("/api/purchases", { data: purchase })).ok()).toBe(true);
    await expect.poll(async () => (await snapshot()).transactions.length, { timeout: 12_000 }).toBe(1);
    expect((await snapshot()).inventory[0].stock).toBe(4);
    await stop(); await start();
    const restored = await snapshot();
    expect(restored.inventory[0].stock).toBe(4);
    expect(restored.transactions[0].id).toBe(purchase.orderId);
    expect(restored.qrScans).toBe(7);
    expect((await (await api.post("/api/purchases", { data: purchase })).json()).status).toBe("completed");
    await api.post("/api/scans", { data: { robotId: "robot-001", sessionId: "restart-visit-0" } });
    expect((await snapshot()).inventory[0].stock).toBe(4);
    expect((await snapshot()).transactions.length).toBe(1);
    expect((await snapshot()).qrScans).toBe(7);
    // Same live Python adapter used by Vendi; no model or audio stubs can supply stock.
    const python = process.env.VENDIGO_TEST_PYTHON || resolve(".venv-vendi/bin/python");
    const output = execFileSync(python, ["-c", `
import asyncio
from vendi.config import VoiceConfig
from vendi.conversation.agent import ConversationAgent
from vendi.conversation.context import VendigoContext
async def main():
    agent = ConversationAgent(VoiceConfig(), VendigoContext('${baseURL}'))
    print((await agent.respond('How many Rice Krispies Treats Original are left?')).text)
    print((await agent.respond('How much is Rice Krispies Treats Original?')).text)
    await agent.close()
asyncio.run(main())
`], { encoding: "utf8", timeout: 10_000 });
    expect(output).toContain("4 left");
    expect(output).toContain("1.00 CAD");

    const context = await browser.newContext();
    const shop = await context.newPage();
    const dashboard = await context.newPage();
    await shop.goto(`${baseURL}/shop`);
    await dashboard.goto(`${baseURL}/dashboard`);
    await expect(shop.getByTestId("product-rice-krispies-original")).toContainText("4 left");
    await expect(dashboard.getByLabel("Rice Krispies Treats Original", { exact: true })).toHaveValue("4");
    const live = execFileSync(python, ["tests/verify_live_inventory.py", "--base-url", baseURL, "--data-dir", directory], { encoding: "utf8", timeout: 30_000 });
    expect(live).toContain("9 left");
    expect(live).toContain("2.25 CAD");
    expect(live).toContain("sold out");
    expect(live).toContain("trouble checking stock");
    // Both pages remain open throughout. Direct file edits have no SSE event;
    // polling must still show the new catalog without a navigation or restart.
    await expect(shop.getByTestId("product-rice-krispies-original")).toContainText("9 left");
    await expect(shop.getByTestId("product-rice-krispies-original")).toContainText("$2.25");
    await expect(dashboard.getByLabel("Rice Krispies Treats Original", { exact: true })).toHaveValue("9");
    await expect(dashboard.getByTestId("kpi-units")).toHaveText("2");
    await expect(dashboard.getByTestId("kpi-revenue")).toHaveText("$2.00");
    await expect(dashboard.getByTestId("sale-live-inventory-test")).toContainText("Rice Krispies Treats Original");
    const path = join(directory, "inventory.json");
    const catalog = JSON.parse(readFileSync(path, "utf8"));
    catalog.products[0].inventory = 0;
    writeFileSync(path, JSON.stringify(catalog));
    await expect(shop.getByTestId("product-rice-krispies-original").getByRole("button")).toBeDisabled();
    await expect(shop.getByTestId("product-rice-krispies-original")).toContainText("Sold out");
    await expect(dashboard.getByLabel("Rice Krispies Treats Original", { exact: true })).toHaveValue("0");
    // File-only revisions are in memory; a restart must not make an open page
    // reject new snapshots with a lower revision from the replacement process.
    await stop(); await start();
    catalog.products[0].inventory = 6;
    writeFileSync(path, JSON.stringify(catalog));
    await expect(shop.getByTestId("product-rice-krispies-original")).toContainText("6 left");
    await expect(dashboard.getByLabel("Rice Krispies Treats Original", { exact: true })).toHaveValue("6");
    await context.close();
  } finally {
    await stop(); await api.dispose(); rmSync(directory, { recursive: true, force: true });
  }
});
