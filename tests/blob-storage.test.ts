import test from "node:test";
import assert from "node:assert/strict";
import { setTimeout as delay } from "node:timers/promises";
import { MockAgent, getGlobalDispatcher, setGlobalDispatcher } from "undici";
import { BlobStateStorage, StorageConflict, vercelObjectClient, type JsonObjectClient } from "../src/lib/server/blob-storage.ts";
import { BlobStore } from "../src/lib/server/blob-store.ts";
import { blobPath, storageMode } from "../src/lib/server/storage-config.ts";
import { metrics } from "../src/lib/metrics.ts";
import { inventoryFromSnapshot } from "../src/agent/live-inventory.ts";
import type { RobotHardware } from "../src/lib/robot/hardware.ts";

class ObjectService implements JsonObjectClient {
  value: unknown = null;
  revision = 0;
  fail = false;
  async read() { return this.value === null ? null : { value: structuredClone(this.value), etag: String(this.revision) }; }
  async write(_path: string, value: unknown, etag: string | null) {
    if (this.fail) throw new Error("Storage unavailable");
    if (etag === null ? this.value !== null : etag !== String(this.revision)) throw new StorageConflict();
    this.value = structuredClone(value); this.revision++;
  }
}
const noop = async () => {};
const hardware: RobotHardware = { unlockCompartment: noop, lockCompartment: noop, stopRobot: noop, resumeRobot: noop, returnToBase: noop };
const input = { orderId: "blob-order", productId: "rice-krispies-original", robotId: "robot-001", compartmentId: 1, sessionId: "visit-1" };
function fixture(adapter = hardware, duration = 10) {
  const service = new ObjectService();
  const storage = () => new BlobStateStorage("test/state.json", service);
  return { service, storage, open: () => new BlobStore(storage(), adapter, duration) };
}

test("Vercel selects Blob before touching local paths and fails clearly if unconfigured", () => {
  assert.equal(storageMode({}), "json");
  assert.equal(storageMode({ VERCEL: "1", BLOB_READ_WRITE_TOKEN: "configured" }), "blob");
  assert.throws(() => storageMode({ VERCEL: "1", VENDIGO_DATA_DIR: "/var/task/data" }), /private Vercel Blob/);
  assert.throws(() => storageMode({ VERCEL: "1", VENDIGO_STORAGE: "json" }), /cannot persist/);
  assert.notEqual(blobPath({ VERCEL_ENV: "preview" }), blobPath({ VERCEL_ENV: "production" }));
});

test("racing cold starts create one seven-snack catalog without resetting edits", async () => {
  const f = fixture();
  const snapshots = await Promise.all(Array.from({ length: 8 }, () => f.open().snapshot()));
  assert.equal(f.service.revision, 1);
  assert.ok(snapshots.every((s) => s.products.length === 7 && s.inventory.reduce((sum, p) => sum + p.stock, 0) === 16));
  await f.open().setInventory("robot-001", [{ productId: input.productId, stock: 5 }]);
  assert.equal((await f.open().snapshot()).inventory[0].stock, 5);
});

test("Blob admin changes, purchases, prices and sold-out status reach Vendi without a startup cache", async () => {
  const f = fixture(); const voiceInstance = f.open(); const admin = f.open();
  const facts = async () => inventoryFromSnapshot(await voiceInstance.snapshot())[0];
  await admin.setInventory("robot-001", [{ productId: input.productId, stock: 3 }]);
  assert.equal((await facts()).quantity, 3);
  const shop = f.open(); await shop.purchase(input); await shop.finishPickup(input.orderId);
  assert.equal((await facts()).quantity, 2);
  await admin.setInventory("robot-001", [{ productId: input.productId, stock: 9 }]);
  assert.equal((await facts()).quantity, 9);
  await f.storage().update((data) => { data.state.products[0].priceCents = 225; data.state.revision++; });
  assert.equal((await facts()).priceCents, 225);
  await admin.setInventory("robot-001", [{ productId: input.productId, stock: 0 }]);
  assert.equal((await facts()).available, false);
  await assert.rejects(f.open().purchase({ ...input, orderId: "sold-out" }), /sold out/);
  await assert.rejects(admin.setInventory("robot-001", [{ productId: input.productId, stock: -1 }]), /whole numbers/);
});

test("two instances cannot oversell, and racing duplicate callbacks only open/close/decrement once", async () => {
  let opens = 0; let closes = 0;
  const f = fixture({ ...hardware, unlockCompartment: async () => { opens++; await delay(20); }, lockCompartment: async () => { closes++; await delay(20); } }, 100);
  await f.open().setInventory("robot-001", [{ productId: input.productId, stock: 1 }]);
  const first = f.open(), second = f.open();
  await Promise.all([first.purchase(input), second.purchase(input)]);
  assert.equal(opens, 1);
  await assert.rejects(second.purchase({ ...input, orderId: "other-order" }), /busy/);
  await assert.rejects(second.setInventory("robot-001", [{ productId: input.productId, stock: 10 }]), /pickup/);
  await Promise.all([first.finishPickup(input.orderId), second.finishPickup(input.orderId)]);
  assert.equal(closes, 1);
  assert.equal((await second.purchase(input)).status, "completed");
  assert.equal((await first.snapshot()).inventory[0].stock, 0);
  assert.equal((await second.snapshot()).transactions.length, 1);
  await assert.rejects(second.purchase({ ...input, sessionId: "forged" }), /already in use/);
});

test("concurrent scans are deduplicated and retained with purchase metrics across cold starts", async () => {
  const f = fixture();
  await Promise.all(Array.from({ length: 7 }, (_, i) => f.open().scan("robot-001", `session-${i}`)));
  await Promise.all(Array.from({ length: 5 }, () => f.open().scan("robot-001", "session-0")));
  const shop = f.open(); await shop.purchase(input); await shop.finishPickup(input.orderId);
  const snapshot = await f.open().snapshot(); const totals = metrics(snapshot);
  assert.equal(snapshot.qrScans, 7); assert.equal(snapshot.transactions.length, 1);
  assert.equal(snapshot.transactions[0].id, input.orderId);
  assert.equal(totals.revenueCents, 100);
  assert.equal(totals.conversion, 1 / 7 * 100);
});

test("a lost worker is recovered by another instance, without reopening or duplicate completion", async () => {
  let opens = 0;
  const f = fixture({ ...hardware, unlockCompartment: async () => { opens++; } });
  await f.open().purchase(input);
  await delay(25); // the original instance disappears without running its after task
  const snapshot = await f.open().snapshot();
  assert.equal(snapshot.inventory[0].stock, 2); assert.equal(snapshot.transactions.length, 1);
  assert.equal((await f.open().purchase(input)).status, "completed");
  assert.equal(opens, 1);
});

test("an interrupted opening is closed without fabricating a purchase", async () => {
  let opens = 0; let closes = 0;
  const f = fixture({ ...hardware, unlockCompartment: async () => { opens++; }, lockCompartment: async () => { closes++; } });
  await f.open().purchase(input);
  await f.storage().update((data) => {
    data.orders[0].status = "opening"; delete data.orders[0].openedAt;
    data.orders[0].closesAt = null; data.orders[0].operationExpiresAt = 1;
  });
  const result = await f.open().getOrder(input.orderId);
  assert.equal(result.status, "failed"); assert.equal(opens, 1); assert.equal(closes, 1);
  assert.equal((await f.open().snapshot()).transactions.length, 0);
});

test("failure to persist a reservation never opens hardware or reports a purchase", async () => {
  let opens = 0;
  const f = fixture({ ...hardware, unlockCompartment: async () => { opens++; } });
  await f.open().snapshot(); f.service.fail = true;
  await assert.rejects(f.open().purchase(input), /Storage unavailable/);
  f.service.fail = false;
  assert.equal(opens, 0); assert.equal((await f.open().snapshot()).transactions.length, 0);
});

test("corrupt shared JSON fails closed instead of replacing it with seed stock", async () => {
  const f = fixture(); await f.open().snapshot();
  f.service.value = { version: 1, inventory: "broken" }; const writes = f.service.revision;
  await assert.rejects(f.open().snapshot(), /products array/);
  assert.equal(f.service.revision, writes);
});

test("the real Blob SDK bypasses cache and sends conditional private writes", async (t) => {
  const token = process.env.BLOB_READ_WRITE_TOKEN;
  process.env.BLOB_READ_WRITE_TOKEN = "vercel_blob_rw_teststore_fake";
  t.after(() => { if (token === undefined) delete process.env.BLOB_READ_WRITE_TOKEN; else process.env.BLOB_READ_WRITE_TOKEN = token; });
  const dispatcher = getGlobalDispatcher(); const mock = new MockAgent();
  mock.disableNetConnect(); setGlobalDispatcher(mock);
  t.after(async () => { setGlobalDispatcher(dispatcher); await mock.close(); });
  mock.get("https://teststore.private.blob.vercel-storage.com").intercept({ path: "/test.json?cache=0" })
    .reply(200, { version: 1 }, { headers: { etag: "v1" } });
  mock.get("https://vercel.com").intercept({ path: "/api/blob/?pathname=test.json", method: "PUT", headers: { "x-if-match": "v1", "x-allow-overwrite": "1", "x-vercel-blob-access": "private" } })
    .reply(200, { url: "https://teststore.private.blob.vercel-storage.com/test.json", pathname: "test.json", etag: "v2" });
  mock.get("https://vercel.com").intercept({ path: "/api/blob/?pathname=new.json", method: "PUT", headers: { "x-allow-overwrite": "0", "x-vercel-blob-access": "private" } })
    .reply(200, { url: "https://teststore.private.blob.vercel-storage.com/new.json", pathname: "new.json", etag: "v1" });
  assert.equal((await vercelObjectClient.read("test.json"))?.etag, "v1");
  await vercelObjectClient.write("test.json", { version: 1 }, "v1");
  await vercelObjectClient.write("new.json", { version: 1 }, null);
  mock.assertNoPendingInterceptors();
});
