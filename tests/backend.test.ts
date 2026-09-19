import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import { DemoStore, AppError } from "../src/lib/server/store.ts";
import type { RobotHardware } from "../src/lib/robot/hardware.ts";

const hardware: RobotHardware = {
  unlockCompartment: async () => {}, lockCompartment: async () => {},
  stopRobot: async () => {}, resumeRobot: async () => {}, returnToBase: async () => {},
};
const input = { orderId: "test-order", robotId: "robot-001", productId: "coke", compartmentId: 1, sessionId: "test-session" };

test("all products and seeded transactions are free", () => {
  const store = new DemoStore(hardware);
  const snapshot = store.snapshot();
  assert.equal(snapshot.transactions.length, 97);
  assert.ok(snapshot.products.every((product) => product.priceCents === 0));
  assert.ok(snapshot.transactions.every((transaction) => transaction.amountCents === 0));
  assert.equal(snapshot.transactions.reduce((sum, t) => sum + t.amountCents, 0), 0);
  assert.equal(snapshot.qrScans, 143);
  assert.equal((snapshot.purchasingSessions / snapshot.qrScans * 100).toFixed(1), "67.8");
  assert.equal(snapshot.inventory.reduce((sum, item) => sum + item.stock, 0), 34);
});

test("QR visits are deduplicated per robot and browser session", () => {
  const store = new DemoStore(hardware);
  store.scan("robot-001", "a"); store.scan("robot-001", "a"); store.scan("robot-001", "b");
  assert.equal(store.snapshot().qrScans, 145);
  assert.throws(() => store.scan("unknown", "a"), (error) => error instanceof AppError && error.status === 404);
});

test("pickup relocks on the server, records one sale, and broadcasts every metric", async (t) => {
  let locks = 0;
  const store = new DemoStore({ ...hardware, lockCompartment: async () => { locks++; } }, 30);
  t.after(() => store.dispose());
  const revisions: number[] = [];
  const unsubscribe = store.subscribe((state) => revisions.push(state.revision));
  const order = await store.purchase(input);
  assert.equal(order.status, "unlocked");
  assert.equal(store.snapshot().inventory[0].stock, 8);
  assert.equal(store.snapshot().transactions.length, 97);
  // Relocking works without a connected customer or event-stream subscriber.
  unsubscribe();
  await delay(70);
  const snapshot = store.snapshot();
  assert.equal(locks, 1);
  assert.equal(store.getOrder(order.id).status, "completed");
  assert.equal(snapshot.inventory[0].stock, 7);
  assert.equal(snapshot.transactions.length, 98);
  assert.equal(snapshot.transactions[0].amountCents, 0);
  assert.equal(snapshot.transactions.reduce((sum, sale) => sum + sale.amountCents, 0), 0);
  assert.equal(snapshot.transactions[0].locationId, "hacking");
  assert.equal(snapshot.transactions.filter((sale) => sale.locationId === "hacking").length, 40);
  assert.equal(snapshot.purchasingSessions, 98);
  assert.equal(snapshot.qrScans, 144);
  assert.equal(snapshot.activeOrders.length, 0);
  assert.equal(snapshot.robots[0].status, "available");
  assert.ok(revisions.length >= 3);
});

test("concurrent shoppers cannot oversell or open two compartments", async (t) => {
  const store = new DemoStore({ ...hardware, unlockCompartment: async () => { await delay(15); } });
  t.after(() => store.dispose());
  const results = await Promise.allSettled([store.purchase(input), store.purchase({ ...input, orderId: "other-order", sessionId: "other-customer" })]);
  assert.equal(results.filter((r) => r.status === "fulfilled").length, 1);
  assert.equal(results.filter((r) => r.status === "rejected").length, 1);
  assert.equal(store.snapshot().activeOrders.length, 1);
  await assert.rejects(store.command("robot-001", "return-to-base"), /relock/);
  await store.close(input.orderId);
  assert.equal(store.snapshot().transactions.length, 98);
});

test("repeated requests and relock callbacks are idempotent", async (t) => {
  let unlocks = 0;
  const store = new DemoStore({ ...hardware, unlockCompartment: async () => { unlocks++; await delay(5); } });
  t.after(() => store.dispose());
  await Promise.all([store.purchase(input), store.purchase(input)]);
  await store.close(input.orderId);
  await store.close(input.orderId);
  const result = await store.purchase(input);
  assert.equal(result.status, "completed");
  assert.equal(unlocks, 1);
  assert.equal(store.snapshot().transactions.length, 98);
  await assert.rejects(store.purchase({ ...input, productId: "water" }), /already in use/);
});

test("repeat purchases keep session conversion at or below 100 percent", async (t) => {
  const store = new DemoStore(hardware);
  t.after(() => store.dispose());
  await store.purchase(input); await store.close(input.orderId);
  await store.purchase({ ...input, orderId: "second-item" }); await store.close("second-item");
  const snapshot = store.snapshot();
  assert.equal(snapshot.transactions.length, 99);
  assert.equal(snapshot.purchasingSessions, 98);
  assert.equal(snapshot.qrScans, 144);
});

test("invalid compartments and exhausted stock are rejected", async (t) => {
  const store = new DemoStore(hardware);
  t.after(() => store.dispose());
  await assert.rejects(store.purchase({ ...input, compartmentId: 9 }), /do not match/);
  await assert.rejects(store.purchase({ ...input, robotId: "unknown" }), /could not be found/);
  for (let i = 0; i < 4; i++) {
    await store.purchase({ ...input, orderId: `zero-${i}`, productId: "coke-zero", compartmentId: 2 });
    await store.close(`zero-${i}`);
  }
  await assert.rejects(store.purchase({ ...input, orderId: "sold-out", productId: "coke-zero", compartmentId: 2 }), /sold out/);
  assert.equal(store.snapshot().inventory[1].stock, 0);
});

test("unlock failures release the reservation without inventory or revenue changes", async () => {
  const store = new DemoStore({ ...hardware, unlockCompartment: async () => { throw new Error("Unreachable"); } });
  const order = await store.purchase(input);
  assert.equal(order.status, "failed");
  assert.equal(store.snapshot().inventory[0].stock, 8);
  assert.equal(store.snapshot().transactions.length, 97);
  assert.equal(store.snapshot().robots[0].status, "available");
});

test("a failed relock stops sales and can be retried exactly once", async (t) => {
  let failLock = true;
  const store = new DemoStore({ ...hardware, lockCompartment: async () => { if (failLock) throw new Error("Obstruction"); } });
  t.after(() => store.dispose());
  await store.purchase(input); await store.close(input.orderId);
  assert.equal(store.getOrder(input.orderId).status, "lock_failed");
  assert.equal(store.snapshot().robots[0].status, "stopped");
  assert.equal(store.snapshot().inventory[0].stock, 8);
  await assert.rejects(store.command("robot-001", "resume"), /relock/);
  failLock = false;
  await store.command("robot-001", "retry-lock");
  assert.equal(store.getOrder(input.orderId).status, "completed");
  assert.equal(store.snapshot().inventory[0].stock, 7);
  assert.equal(store.snapshot().transactions.length, 98);
  assert.equal(store.snapshot().robots[0].status, "stopped");
  await store.command("robot-001", "resume");
  assert.equal(store.snapshot().robots[0].status, "available");
});

test("manual unlocks do not record a sale or silently resume a stopped robot", async (t) => {
  const store = new DemoStore(hardware);
  t.after(() => store.dispose());
  await store.command("robot-001", "stop");
  await assert.rejects(store.purchase(input), /busy/);
  const order = await store.command("robot-001", "unlock", 3);
  assert.ok(order);
  await store.close(order.id);
  assert.equal(store.snapshot().inventory[2].stock, 7);
  assert.equal(store.snapshot().transactions.length, 97);
  assert.equal(store.snapshot().robots[0].status, "stopped");
  await store.command("robot-001", "resume");
  await store.command("robot-001", "return-to-base");
  assert.equal(store.snapshot().robots[0].status, "returning");
});

test("an emergency stop takes precedence over an in-flight resume", async () => {
  let acknowledgeResume!: () => void;
  const store = new DemoStore({ ...hardware, resumeRobot: () => new Promise<void>((resolve) => { acknowledgeResume = resolve; }) });
  await store.command("robot-001", "stop");
  const resuming = store.command("robot-001", "resume");
  await store.command("robot-001", "stop");
  acknowledgeResume();
  await resuming;
  assert.equal(store.snapshot().robots[0].status, "stopped");
});

test("all seven original ESP32 camera files remain byte-for-byte unchanged", () => {
  const hashes: Record<string, string> = {
    "CameraWebServer_htn.ino": "cbac28e0ea77de867f8039f8368097548a1754d0112cb5318a6f242faee96da0",
    "app_httpd.cpp": "2bc1f5c1ba2b60d72e6df82220f366edf1b706e75efc14e20116b0374c9b27fa",
    "board_config.h": "ff8d24756f7d18a8dd456cb0149fb5949a038a0c72bd232a95496b7976849c7a",
    "camera_index.h": "c31bc07d50b88f23eb41378abdb898f84c1caee76bf8b4e28c1404abb2b5055e",
    "camera_pins.h": "71de6987ee84a6d119596f3b52c8aead1b4a8e48cf4a7c3e1f39cc050ecf2754",
    "ci.yml": "09bb372db771f68661ba8756934f6a49b364250be664a877677c4686187a365b",
    "partitions.csv": "555f2122d7a0af9067fd6fb1a97a6bb1b59177a53f4d48d44b96ecf320f88c91",
  };
  for (const [file, expected] of Object.entries(hashes)) {
    const bytes = readFileSync(new URL(`../camera_code/CameraWebServer_htn/${file}`, import.meta.url));
    assert.equal(createHash("sha256").update(bytes).digest("hex"), expected, file);
  }
});
