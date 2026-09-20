import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import { DemoStore, AppError } from "../src/lib/server/store.ts";
import { robotHardware, type RobotHardware } from "../src/lib/robot/hardware.ts";

const hardware: RobotHardware = {
  unlockCompartment: async () => {}, lockCompartment: async () => {},
  stopRobot: async () => {}, resumeRobot: async () => {}, returnToBase: async () => {},
};
const input = { orderId: "test-order", robotId: "robot-001", productId: "rice-krispies-original", compartmentId: 1, sessionId: "test-session" };

test("all catalog products cost one dollar and analytics start without fake events", () => {
  const store = new DemoStore(hardware);
  const snapshot = store.snapshot();
  assert.equal(snapshot.transactions.length, 0);
  assert.ok(snapshot.products.every((product) => product.priceCents === 100));
  assert.ok(snapshot.transactions.every((transaction) => transaction.amountCents === 100));
  assert.equal(snapshot.transactions.reduce((sum, t) => sum + t.amountCents, 0), 0);
  assert.equal(snapshot.qrScans, 0);
  assert.equal(snapshot.purchasingSessions, 0);
  assert.equal(snapshot.inventory.reduce((sum, item) => sum + item.stock, 0), 16);
});

test("QR visits are deduplicated per robot and browser session", () => {
  const store = new DemoStore(hardware);
  store.scan("robot-001", "a"); store.scan("robot-001", "a"); store.scan("robot-001", "b");
  assert.equal(store.snapshot().qrScans, 2);
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
  assert.equal(store.snapshot().inventory[0].stock, 3);
  assert.equal(store.snapshot().transactions.length, 0);
  // Relocking works without a connected customer or event-stream subscriber.
  unsubscribe();
  await delay(70);
  const snapshot = store.snapshot();
  assert.equal(locks, 1);
  assert.equal(store.getOrder(order.id).status, "completed");
  assert.equal(snapshot.inventory[0].stock, 2);
  assert.equal(snapshot.transactions.length, 1);
  assert.equal(snapshot.transactions[0].amountCents, 100);
  assert.equal(snapshot.transactions.reduce((sum, sale) => sum + sale.amountCents, 0), 100);
  assert.equal(snapshot.transactions[0].locationId, "hacking");
  assert.equal(snapshot.transactions.filter((sale) => sale.locationId === "hacking").length, 1);
  assert.equal(snapshot.purchasingSessions, 1);
  assert.equal(snapshot.qrScans, 0);
  assert.equal(snapshot.activeOrders.length, 0);
  assert.equal(snapshot.robots[0].status, "available");
  assert.ok(revisions.length >= 2);
});

test("a purchase opens the real lid adapter and its server timer closes it without browser requests", async (t) => {
  const oldUrl = process.env.LID_API_URL;
  const oldKey = process.env.LID_API_KEY;
  process.env.LID_API_URL = "https://lid.example.invalid/api/v1/lid";
  process.env.LID_API_KEY = "test-lid-api-key-".repeat(4);
  t.after(() => {
    if (oldUrl === undefined) delete process.env.LID_API_URL; else process.env.LID_API_URL = oldUrl;
    if (oldKey === undefined) delete process.env.LID_API_KEY; else process.env.LID_API_KEY = oldKey;
  });
  const commands: string[] = [];
  let rejectClose = false;
  let wrongPosition = false;
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.equal(url, process.env.LID_API_URL);
    assert.equal(init.method, "POST");
    assert.equal(new Headers(init.headers).get("Authorization"), `Bearer ${process.env.LID_API_KEY}`);
    const { state } = JSON.parse(String(init.body));
    commands.push(state);
    if (state === "closed" && rejectClose) return new Response("offline", { status: 502 });
    return Response.json({ commanded_state: wrongPosition ? "unknown" : state, commanded_angle: state === "open" ? 0 : 180, enabled: true, position_feedback: false });
  });
  const store = new DemoStore(robotHardware, 25);
  t.after(() => store.dispose());
  const order = await store.purchase(input);
  assert.equal(order.status, "unlocked");
  assert.deepEqual(commands, ["open"]);
  // Retrying the purchase must not reopen the lid or extend its deadline.
  assert.equal((await store.purchase(input)).closesAt, order.closesAt);
  await delay(75);
  assert.deepEqual(commands, ["open", "closed"]);
  assert.equal(store.getOrder(order.id).status, "completed");
  assert.equal(store.snapshot().inventory[0].stock, 2);
  rejectClose = true;
  const failed = await store.purchase({ ...input, orderId: "close-failure" });
  await delay(75);
  assert.equal(store.getOrder(failed.id).status, "lock_failed");
  assert.equal(store.snapshot().inventory[0].stock, 2);
  rejectClose = false;
  await store.command("robot-001", "retry-lock");
  assert.equal(store.getOrder(failed.id).status, "completed");
  wrongPosition = true;
  await assert.rejects(robotHardware.unlockCompartment("robot-001", 1), /did not acknowledge/);
  process.env.LID_API_KEY = "too-short";
  const count = commands.length;
  await assert.rejects(robotHardware.unlockCompartment("robot-001", 1), /not configured/);
  assert.equal(commands.length, count);
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
  assert.equal(store.snapshot().transactions.length, 1);
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
  assert.equal(store.snapshot().transactions.length, 1);
  await assert.rejects(store.purchase({ ...input, productId: "biscoff-cookies" }), /already in use/);
});

test("repeat purchases do not fabricate shop visits", async (t) => {
  const store = new DemoStore(hardware);
  t.after(() => store.dispose());
  await store.purchase(input); await store.close(input.orderId);
  await store.purchase({ ...input, orderId: "second-item" }); await store.close("second-item");
  const snapshot = store.snapshot();
  assert.equal(snapshot.transactions.length, 2);
  assert.equal(snapshot.purchasingSessions, 1);
  assert.equal(snapshot.qrScans, 0);
});

test("invalid compartments and exhausted stock are rejected", async (t) => {
  const store = new DemoStore(hardware);
  t.after(() => store.dispose());
  await assert.rejects(store.purchase({ ...input, compartmentId: 9 }), /do not match/);
  await assert.rejects(store.purchase({ ...input, robotId: "unknown" }), /could not be found/);
  for (let i = 0; i < 4; i++) {
    await store.purchase({ ...input, orderId: `zero-${i}`, productId: "kirkland-granola-bar", compartmentId: 4 });
    await store.close(`zero-${i}`);
  }
  await assert.rejects(store.purchase({ ...input, orderId: "sold-out", productId: "kirkland-granola-bar", compartmentId: 4 }), /sold out/);
  assert.equal(store.snapshot().inventory[3].stock, 0);
});

test("unlock failures release the reservation without inventory or revenue changes", async () => {
  const store = new DemoStore({ ...hardware, unlockCompartment: async () => { throw new Error("Unreachable"); } });
  const order = await store.purchase(input);
  assert.equal(order.status, "failed");
  assert.equal(store.snapshot().inventory[0].stock, 3);
  assert.equal(store.snapshot().transactions.length, 0);
  assert.equal(store.snapshot().robots[0].status, "available");
});

test("a failed relock stops sales and can be retried exactly once", async (t) => {
  let failLock = true;
  const store = new DemoStore({ ...hardware, lockCompartment: async () => { if (failLock) throw new Error("Obstruction"); } });
  t.after(() => store.dispose());
  await store.purchase(input); await store.close(input.orderId);
  assert.equal(store.getOrder(input.orderId).status, "lock_failed");
  assert.equal(store.snapshot().robots[0].status, "stopped");
  assert.equal(store.snapshot().inventory[0].stock, 3);
  await assert.rejects(store.command("robot-001", "resume"), /relock/);
  failLock = false;
  await store.command("robot-001", "retry-lock");
  assert.equal(store.getOrder(input.orderId).status, "completed");
  assert.equal(store.snapshot().inventory[0].stock, 2);
  assert.equal(store.snapshot().transactions.length, 1);
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
  assert.equal(store.snapshot().inventory[2].stock, 2);
  assert.equal(store.snapshot().transactions.length, 0);
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
