import { setTimeout as delay } from "node:timers/promises";
import { robotHardware, type RobotHardware } from "../robot/hardware.ts";
import type { AppSnapshot, RobotCommand } from "../../types/index.ts";
import { DemoStore, AppError, type PurchaseInput } from "./store.ts";
import { BlobStateStorage } from "./blob-storage.ts";
import type { StoredState } from "./storage.ts";

/** Reuses the local store's validation and canonical purchase commit. Only the
 * persistence/lifecycle changes: mutations use CAS, IO runs after the commit.
 */
export class BlobStore {
  private storage: BlobStateStorage;
  private hardware: RobotHardware;
  private duration: number;
  constructor(storage: BlobStateStorage, hardware: RobotHardware = robotHardware, duration = 7_000) {
    this.storage = storage; this.hardware = hardware; this.duration = duration;
  }

  private edit<T>(action: (store: DemoStore) => T) {
    return this.storage.update((data) => {
      const staged = new DemoStore(this.hardware, this.duration, {
        load: () => data,
        save: (next) => { Object.assign(data, structuredClone(next)); },
      }, false);
      try { return action(staged); }
      finally { staged.dispose(); }
    });
  }

  private snapshotOf(data: StoredState): AppSnapshot {
    return { ...data.state, serverInstanceId: `blob:${data.state.startedAt}`,
      activeOrders: data.orders.filter((order) => !["completed", "failed"].includes(order.status)) };
  }

  async snapshot() {
    const current = await this.storage.read();
    const due = current.data.orders.filter((order) =>
      (order.status === "unlocked" && (order.closesAt ?? 0) <= Date.now()) ||
      (["opening", "locking"].includes(order.status) && (order.operationExpiresAt ?? 0) <= Date.now()));
    // Recover an interrupted function using the durable order, never a new order.
    for (const order of due) await this.close(order.id);
    return this.snapshotOf(due.length ? (await this.storage.read()).data : current.data);
  }

  async scan(robotId: string, sessionId: string) {
    await this.edit((store) => store.scan(robotId, sessionId));
  }

  async setInventory(robotId: string, items: Parameters<DemoStore["setInventory"]>[1]) {
    await this.edit((store) => store.setInventory(robotId, items));
    return this.snapshot();
  }

  async getOrder(id: string) {
    await this.snapshot();
    const { data } = await this.storage.read();
    const order = data.orders.find((order) => order.id === id);
    if (!order) throw new AppError("Order not found. Please choose your item again.", 404);
    return order;
  }

  async purchase(input: PurchaseInput) {
    await this.snapshot();
    const reservation = await this.edit((store) => store.reservePurchase(input));
    if (!reservation.created) return reservation.order;
    try { await this.hardware.unlockCompartment(reservation.order.robotId, reservation.order.compartmentId); }
    catch { return this.edit((store) => store.failUnlock(input.orderId)); }
    try { return await this.edit((store) => store.acknowledgeUnlock(input.orderId)); }
    catch (error) {
      // If acknowledgement persistence fails, close safely. Recovery never opens
      // again and only records a purchase if an acknowledgement was committed.
      await this.hardware.lockCompartment(reservation.order.robotId, reservation.order.compartmentId).catch(() => {});
      throw error;
    }
  }

  async close(id: string) {
    const claim = await this.edit((store) => store.beginClose(id));
    if (!claim) return;
    let failed = false;
    try { await this.hardware.lockCompartment(claim.robotId, claim.compartmentId); }
    catch { failed = true; }
    await this.edit((store) => store.finishClose(id, claim.operationExpiresAt!, failed));
  }

  /** Called through Next after(), which keeps Vercel alive after the response. */
  async finishPickup(id: string) {
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const { data } = await this.storage.read();
        const order = data.orders.find((o) => o.id === id);
        if (!order || ["completed", "failed", "lock_failed"].includes(order.status)) return;
        // Another function owns an unexpired close claim. Its after task will
        // finish it; expired claims remain recoverable by the next state query.
        if (order.status === "locking" && (order.operationExpiresAt ?? 0) > Date.now()) return;
        const deadline = order.status === "unlocked" ? order.closesAt : order.operationExpiresAt;
        await delay(Math.max(0, (deadline ?? Date.now()) - Date.now()));
        await this.close(id);
      } catch (error) {
        if (attempt === 2) throw error;
        await delay(500);
      }
    }
  }

  async command(robotId: string, command: RobotCommand): Promise<void> {
    if (command !== "retry-lock") throw new AppError("Robot movement controls are disabled in the hosted retail demo.", 410);
    const { data } = await this.storage.read();
    const order = data.orders.find((o) => o.robotId === robotId && o.status === "lock_failed");
    if (!order) throw new AppError("No compartment needs a lock retry.", 409);
    await this.close(order.id);
  }
}
