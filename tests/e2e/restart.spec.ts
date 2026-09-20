import { test, expect } from "@playwright/test";
import { spawn, type ChildProcess, execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { once } from "node:events";
import type { AppSnapshot } from "../../src/types";

// Actual backend processes, with their own data file; never use the operator's data.
test("backend restarts preserve inventory, seven visits, recent purchase and duplicate order protection", async ({ playwright }) => {
  test.setTimeout(60_000);
  const directory = mkdtempSync(join(tmpdir(), "vendigo-restart-"));
  const baseURL = "http://127.0.0.1:3120";
  const api = await playwright.request.newContext({ baseURL });
  let server: ChildProcess | undefined;
  let logs = "";
  const stop = async () => {
    if (server && server.exitCode === null) { const done = once(server, "exit"); server.kill("SIGTERM"); await done; }
  };
  const start = async () => {
    server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3120"], {
      env: { ...process.env, VENDIGO_DATA_FILE: join(directory, "state.json"), LID_API_URL: "", LID_API_ONLY: "" },
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
    expect((await api.post("/api/inventory", { data: { robotId: "robot-001", items: [{ productId: "coke", stock: 5 }] } })).ok()).toBe(true);
    for (let i = 0; i < 7; i++) await api.post("/api/scans", { data: { robotId: "robot-001", sessionId: `restart-visit-${i}` } });
    await stop(); await start();
    expect((await snapshot()).inventory[0].stock).toBe(5);
    expect((await snapshot()).qrScans).toBe(7);
    const purchase = { orderId: "restart-purchase", robotId: "robot-001", productId: "coke", compartmentId: 1, sessionId: "restart-visit-0" };
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
    print((await agent.respond('How many Cokes are left?')).text)
    print((await agent.respond('How much is Coke?')).text)
    await agent.close()
asyncio.run(main())
`], { encoding: "utf8", timeout: 10_000 });
    expect(output).toContain("4 left");
    expect(output).toContain("1.00 CAD");
  } finally {
    await stop(); await api.dispose(); rmSync(directory, { recursive: true, force: true });
  }
});
