import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { DemoStore } from "../src/lib/server/store.ts";
import { JsonStateStorage } from "../src/lib/server/storage.ts";
import { metrics } from "../src/lib/metrics.ts";
import type { RobotHardware } from "../src/lib/robot/hardware.ts";

const hardware: RobotHardware = {
  unlockCompartment: async () => {}, lockCompartment: async () => {},
  stopRobot: async () => {}, resumeRobot: async () => {}, returnToBase: async () => {},
};
const input = { orderId: "durable-order", robotId: "robot-001", productId: "rice-krispies-original", compartmentId: 1, sessionId: "visit-1" };
function fixture(t: test.TestContext) {
  const directory = mkdtempSync(join(tmpdir(), "vendigo-store-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const storage = new JsonStateStorage(directory);
  const stores: DemoStore[] = [];
  t.after(() => stores.forEach((store) => store.dispose()));
  return { storage, open(duration = 7_000) { const store = new DemoStore(hardware, duration, storage); stores.push(store); return store; } };
}

test("inventory.json is the live catalog: hand edits change quantities, prices and availability without restart", (t) => {
  const f = fixture(t); const store = f.open();
  const document = f.storage.inventory.read();
  assert.equal(document.products.length, 7);
  assert.ok(document.products.every((p) => p.price === 1 && p.image.endsWith(".svg")));
  document.products[0].inventory = 9;
  document.products[0].price = 2.25;
  writeFileSync(f.storage.inventory.path, JSON.stringify(document));
  assert.equal(store.snapshot().inventory[0].stock, 9);
  assert.equal(store.snapshot().products[0].priceCents, 225);
  assert.equal(f.storage.inventory.getProduct("Rice Krispies Treats Original").inventory, 9);
  assert.throws(() => f.storage.inventory.getProduct("unknown"), /Unknown product/);
  const revision = store.snapshot().revision;
  document.products[0].inventory = 0;
  writeFileSync(f.storage.inventory.path, JSON.stringify(document));
  assert.equal(store.snapshot().inventory[0].stock, 0);
  assert.ok(store.snapshot().revision > revision);
  assert.ok(!f.storage.inventory.getAvailableProducts().some((p) => p.id === "rice-krispies-original"));
  assert.equal(f.storage.purchases.read().purchases.length, 0);
  assert.equal(f.storage.analytics.read().qr_scans, 0);
  document.products[0].inventory = -1;
  writeFileSync(f.storage.inventory.path, JSON.stringify(document));
  assert.throws(() => store.snapshot(), /nonnegative integer/);
});

test("interrupted multi-file commit recovers a purchase and its decrement together, exactly once", async (t) => {
  const f = fixture(t); let store = f.open();
  await store.purchase(input);
  const write = f.storage.purchases.write.bind(f.storage.purchases);
  let failOnce = true;
  f.storage.purchases.write = (value) => {
    if (value.purchases.length && failOnce) { failOnce = false; throw new Error("interrupted replacement"); }
    write(value);
  };
  await assert.rejects(store.close(input.orderId), /interrupted replacement/);
  assert.equal(f.storage.inventory.getProduct("rice-krispies-original").inventory, 2);
  assert.equal(f.storage.purchases.read().purchases.length, 0);
  assert.ok(existsSync(f.storage.journalPath));
  store.dispose(); store = f.open();
  assert.equal(store.snapshot().inventory[0].stock, 2);
  assert.equal(store.snapshot().transactions.length, 1);
  assert.equal(store.getOrder(input.orderId).status, "completed");
  assert.ok(!existsSync(f.storage.journalPath));
  await store.purchase(input); await store.close(input.orderId);
  assert.equal(store.snapshot().inventory[0].stock, 2);
  assert.equal(f.storage.purchases.getRecent()[0].order_id, input.orderId);
});

test("the previous state.json is imported once without losing saved stock, purchases or visit IDs", async (t) => {
  const f = fixture(t); const store = f.open();
  store.setInventory("robot-001", [{ productId: "rice-krispies-original", stock: 5 }]);
  store.scan("robot-001", "old-visit");
  await store.purchase(input); await store.close(input.orderId);
  const legacy = f.storage.load()!;
  store.dispose();
  const directory = mkdtempSync(join(tmpdir(), "vendigo-legacy-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  writeFileSync(join(directory, "state.json"), JSON.stringify(legacy));
  const storage = new JsonStateStorage(directory);
  const migrated = new DemoStore(hardware, 7000, storage);
  t.after(() => migrated.dispose());
  assert.equal(migrated.snapshot().inventory[0].stock, 4);
  assert.equal(migrated.snapshot().qrScans, 1);
  assert.equal(storage.purchases.read().purchases[0].price, 1);
  assert.equal(storage.analytics.read().visit_ids[0], "robot-001:old-visit");
  assert.ok(!existsSync(join(directory, "state.json")));
  assert.ok(existsSync(join(directory, "state.json.bak")));
  migrated.scan("robot-001", "old-visit");
  await migrated.purchase(input);
  assert.equal(migrated.snapshot().transactions.length, 1);
  assert.equal(migrated.snapshot().qrScans, 1);
});

test("a confirmed order keeps its agreed price while subsequent orders use a catalog edit", async (t) => {
  const f = fixture(t); const store = f.open();
  await store.purchase(input);
  const inventory = f.storage.inventory.read();
  inventory.products[0].price = 2.25;
  writeFileSync(f.storage.inventory.path, JSON.stringify(inventory));
  await store.close(input.orderId);
  assert.equal(store.snapshot().transactions[0].amountCents, 100);
  assert.equal(store.snapshot().products[0].priceCents, 225);
  await store.purchase({ ...input, orderId: "new-price" }); await store.close("new-price");
  assert.equal(store.snapshot().transactions[0].amountCents, 225);
  assert.equal(metrics(store.snapshot()).revenueCents, 325);
});

test("invalid hand-edited inventory is never overwritten even while an existing pickup relocks", async (t) => {
  const f = fixture(t); let locks = 0;
  const store = new DemoStore({ ...hardware, lockCompartment: async () => { locks++; } }, 7000, f.storage);
  t.after(() => store.dispose());
  await store.purchase(input);
  const valid = readFileSync(f.storage.inventory.path, "utf8");
  writeFileSync(f.storage.inventory.path, "{broken");
  await assert.rejects(store.close(input.orderId));
  assert.equal(locks, 1);
  assert.equal(readFileSync(f.storage.inventory.path, "utf8"), "{broken");
  writeFileSync(f.storage.inventory.path, valid);
  await store.close(input.orderId);
  assert.equal(store.snapshot().inventory[0].stock, 2);
  assert.equal(store.snapshot().transactions.length, 1);
});

test("Rice Krispies Treats Original 5 → reload 5 → purchase 4 → reload 4; purchases, seven scans and idempotency persist", async (t) => {
  const f = fixture(t);
  let store = f.open();
  store.setInventory("robot-001", [{ productId: "rice-krispies-original", stock: 5 }]);
  for (let i = 0; i < 7; i++) store.scan("robot-001", `visit-${i}`);
  store.dispose(); store = f.open();
  assert.equal(store.snapshot().inventory[0].stock, 5);
  await store.purchase(input); await store.close(input.orderId);
  store.dispose(); store = f.open();
  assert.equal(store.snapshot().inventory[0].stock, 4);
  assert.equal(store.snapshot().transactions[0].id, input.orderId);
  assert.equal(store.snapshot().transactions[0].productName, "Rice Krispies Treats Original");
  assert.equal(store.snapshot().qrScans, 7);
  store.scan("robot-001", "visit-1");
  await store.purchase(input); await store.close(input.orderId);
  assert.equal(store.snapshot().inventory[0].stock, 4);
  assert.equal(store.snapshot().transactions.length, 1);
  assert.equal(store.snapshot().qrScans, 7);
  await assert.rejects(store.purchase({ ...input, sessionId: "forged" }), /already in use/);
});

test("inventory updates validate every row before mutation, reject negative/fractional quantities, and cannot overwrite a purchase", async (t) => {
  const store = fixture(t).open();
  for (const stock of [-1, 0.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => store.setInventory("robot-001", [{ productId: "rice-krispies-original", stock }]), /whole numbers/);
  }
  assert.throws(() => store.setInventory("robot-001", [{ productId: "rice-krispies-original", stock: 1 }, { productId: "biscoff-cookies", stock: -1 }]));
  assert.equal(store.snapshot().inventory[0].stock, 3);
  await store.purchase(input);
  assert.throws(() => store.setInventory("robot-001", [{ productId: "rice-krispies-original", stock: 10 }]), /pickup/);
  await store.close(input.orderId);
  assert.throws(() => store.setInventory("robot-001", [{ productId: "rice-krispies-original", stock: 10, expectedStock: 3 }]), /Stock changed/);
  assert.equal(store.snapshot().inventory[0].stock, 2);
});

test("sold-out and disabled products cannot be purchased; the last unit cannot be oversold", async (t) => {
  const f = fixture(t); const store = f.open();
  store.setInventory("robot-001", [{ productId: "rice-krispies-original", stock: 0 }]);
  await assert.rejects(store.purchase(input), /sold out/);
  store.setInventory("robot-001", [{ productId: "rice-krispies-original", stock: 1 }]);
  const outcomes = await Promise.allSettled([store.purchase(input), store.purchase({ ...input, orderId: "other" })]);
  assert.equal(outcomes.filter((outcome) => outcome.status === "fulfilled").length, 1);
  await store.close(input.orderId);
  assert.equal(store.snapshot().inventory[0].stock, 0);
  assert.equal(store.snapshot().inventory[1].stock, 3);
  const saved = f.storage.load()!; saved.state.products[1].enabled = false; f.storage.save(saved);
  const reloaded = f.open();
  await assert.rejects(reloaded.purchase({ ...input, orderId: "disabled", productId: "kitkat", compartmentId: 2 }), /unavailable/);
});

test("revenue uses catalog cents, purchase-based conversion handles repeated visits and zero scans", async (t) => {
  const f = fixture(t); let store = f.open();
  assert.equal(metrics(store.snapshot()).conversion, 0);
  const saved = f.storage.load()!; saved.state.products[0].priceCents = 250; f.storage.save(saved);
  store.dispose(); store = f.open();
  store.scan("robot-001", "only-visit");
  await store.purchase(input); await store.close(input.orderId);
  await store.purchase({ ...input, orderId: "second" }); await store.close("second");
  assert.deepEqual(metrics(store.snapshot()), { purchases: 2, revenueCents: 500, qrScans: 1, conversion: 200, itemsRemaining: 14 });
});

test("restart recovers an interrupted pickup without reopening or duplicating it", async (t) => {
  const f = fixture(t); let store = f.open(40);
  await store.purchase(input); store.dispose();
  store = f.open(40);
  await delay(100);
  assert.equal(store.getOrder(input.orderId).status, "completed");
  assert.equal(store.snapshot().transactions.length, 1);
  assert.equal(store.snapshot().inventory[0].stock, 2);
});

test("failed writes do not publish or leave phantom inventory, scans, or purchases", async (t) => {
  const f = fixture(t); let fail = false;
  const store = new DemoStore(hardware, 7000, { load: () => f.storage.load(), save(data) { if (fail) throw new Error("disk full"); f.storage.save(data); } });
  t.after(() => store.dispose());
  let published = 0; store.subscribe(() => published++);
  fail = true;
  assert.throws(() => store.setInventory("robot-001", [{ productId: "rice-krispies-original", stock: 5 }]), /disk full/);
  assert.throws(() => store.scan("robot-001", "failed"), /disk full/);
  assert.equal(store.snapshot().inventory[0].stock, 3);
  assert.equal(store.snapshot().qrScans, 0);
  assert.equal(published, 0);
  fail = false; await store.purchase(input);
  // Fail only the completed-purchase write after the locking status is durable.
  const originalSave = f.storage.save.bind(f.storage);
  f.storage.save = (data) => { if (data.state.transactions.length) throw new Error("disk full"); originalSave(data); };
  await assert.rejects(store.close(input.orderId), /disk full/);
  assert.equal(store.snapshot().inventory[0].stock, 3);
  assert.equal(store.snapshot().transactions.length, 0);
  f.storage.save = originalSave;
  await store.close(input.orderId);
  assert.equal(store.snapshot().inventory[0].stock, 2);
});

test("corrupt JSON is surfaced without overwriting the file", (t) => {
  const f = fixture(t); f.open().dispose();
  writeFileSync(f.storage.inventory.path, '{"broken":');
  assert.throws(() => f.open());
  assert.equal(readFileSync(f.storage.inventory.path, "utf8"), '{"broken":');
});

test("restart closes an unacknowledged opening without inventing a successful purchase", async (t) => {
  const f = fixture(t); f.open().dispose();
  const saved = f.storage.load()!;
  saved.orders = [{ id: input.orderId, robotId: input.robotId, productId: input.productId, compartmentId: 1, sessionId: input.sessionId, locationId: "hacking", status: "opening", closesAt: null, error: null }];
  saved.state.robots[0].status = "selling";
  f.storage.save(saved);
  const store = f.open();
  await delay(40);
  assert.equal(store.getOrder(input.orderId).status, "failed");
  assert.equal(store.snapshot().inventory[0].stock, 3);
  assert.equal(store.snapshot().transactions.length, 0);
});

test("disk failure after unlock cannot cancel automatic relocking", async (t) => {
  const f = fixture(t); let fail = false; let locks = 0;
  const store = new DemoStore({ ...hardware,
    unlockCompartment: async () => { fail = true; },
    lockCompartment: async () => { locks++; fail = false; },
  }, 25, { load: () => f.storage.load(), save(data) { if (fail) throw new Error("disk full"); f.storage.save(data); } });
  t.after(() => store.dispose());
  await assert.rejects(store.purchase(input), /disk full/);
  await delay(75);
  assert.equal(locks, 1);
  assert.equal(store.getOrder(input.orderId).status, "completed");
  assert.equal(store.snapshot().inventory[0].stock, 2);
  assert.equal(store.snapshot().transactions.length, 1);
});
