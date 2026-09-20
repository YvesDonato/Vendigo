import { randomUUID } from "node:crypto";
import { createSeed } from "../demo-data.ts";
import { robotHardware, type RobotHardware } from "../robot/hardware.ts";
import type { AppSnapshot, Order, RobotCommand } from "../../types/index.ts";
import type { StateStorage, StoredState } from "./storage.ts";

export class AppError extends Error {
  status: number;
  constructor(message: string, status = 400) {
    super(message);
    this.status = status;
  }
}

export class DemoStore {
  private state = createSeed();
  private listeners = new Set<(snapshot: AppSnapshot) => void>();
  private sessions = new Set<string>();
  private buyers = new Set<string>();
  private orders = new Map<string, Order>();
  private busy = new Set<string>();
  private commandVersions = new Map<string, number>();
  private timers = new Set<ReturnType<typeof setTimeout>>();
  private hardware: RobotHardware;
  private duration: number;
  private storage?: StateStorage;
  private checkpoint: StoredState;

  constructor(hardware = robotHardware, unlockDurationMs = 7_000, storage?: StateStorage) {
    this.hardware = hardware;
    this.duration = unlockDurationMs;
    this.storage = storage;
    const saved = storage?.load();
    if (saved) this.restore(saved);
    this.checkpoint = this.serialize();
    if (!saved) storage?.save(this.checkpoint);
    // Resume server-owned closing after restart; never send a second open command.
    for (const order of this.orders.values()) {
      if (["completed", "failed"].includes(order.status)) continue;
      this.busy.add(order.robotId);
      if (order.status === "lock_failed") continue;
      order.status = "unlocked";
      this.scheduleClose(order.id, Math.max(0, (order.closesAt ?? Date.now()) - Date.now()));
    }
  }

  private serialize(): StoredState {
    return structuredClone({ version: 1, state: this.state, orders: [...this.orders.values()], sessions: [...this.sessions], buyers: [...this.buyers] });
  }

  private restore(data: StoredState) {
    const saved = structuredClone(data);
    this.state = saved.state;
    this.orders = new Map(saved.orders.map((order) => [order.id, order]));
    this.sessions = new Set(saved.sessions);
    this.buyers = new Set(saved.buyers);
    this.busy = new Set(saved.orders.filter((order) => !["completed", "failed"].includes(order.status)).map((order) => order.robotId));
  }

  private scheduleClose(id: string, delay: number) {
    const timer = setTimeout(() => {
      this.timers.delete(timer);
      void this.close(id).catch((error) => console.error("Vendigo could not persist pickup completion", error));
    }, delay);
    timer.unref?.();
    this.timers.add(timer);
  }

  snapshot(): AppSnapshot {
    return structuredClone({ ...this.state, activeOrders: [...this.orders.values()].filter((o) => !["completed", "failed"].includes(o.status)) });
  }

  subscribe(listener: (snapshot: AppSnapshot) => void) {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }

  private publish() {
    this.state.revision += 1;
    const data = this.serialize();
    try { this.storage?.save(data); }
    catch (error) { this.restore(this.checkpoint); throw error; }
    this.checkpoint = data;
    const snapshot = this.snapshot();
    for (const listener of this.listeners) {
      try { listener(snapshot); }
      catch { this.listeners.delete(listener); }
    }
  }

  private robot(id: string) {
    const robot = this.state.robots.find((r) => r.id === id);
    if (!robot) throw new AppError("This robot could not be found.", 404);
    return robot;
  }

  scan(robotId: string, sessionId: string) {
    this.robot(robotId);
    const key = `${robotId}:${sessionId}`;
    if (!this.sessions.has(key)) {
      this.sessions.add(key);
      this.state.qrScans += 1;
      this.publish();
    }
  }

  setInventory(robotId: string, updates: { productId: string; stock: number; expectedStock?: number }[]) {
    this.robot(robotId);
    if (!Array.isArray(updates) || !updates.length || new Set(updates.map((u) => u?.productId)).size !== updates.length) {
      throw new AppError("Send unique product quantities.");
    }
    const changes = updates.map((update) => {
      if (!update || !Number.isSafeInteger(update.stock) || update.stock < 0) throw new AppError("Quantities must be whole numbers of zero or more.");
      const item = this.state.inventory.find((i) => i.robotId === robotId && i.productId === update.productId);
      if (!item) throw new AppError("Unknown inventory item.", 404);
      if (update.expectedStock !== undefined && update.expectedStock !== item.stock) throw new AppError("Stock changed while you were editing. Reload the saved quantities and try again.", 409);
      if ([...this.orders.values()].some((o) => o.robotId === robotId && o.productId === update.productId && !["completed", "failed"].includes(o.status))) {
        throw new AppError("Wait for this item's pickup to finish before changing its quantity.", 409);
      }
      return { item, stock: update.stock };
    });
    for (const { item, stock } of changes) item.stock = stock;
    this.publish();
    return this.snapshot();
  }

  getOrder(id: string) {
    const order = this.orders.get(id);
    if (!order) throw new AppError("Order not found. Please choose your item again.", 404);
    return structuredClone(order);
  }

  async purchase(input: { orderId: string; robotId: string; productId: string; compartmentId: number; sessionId: string }) {
    const previous = this.orders.get(input.orderId);
    if (previous) {
      if (previous.robotId !== input.robotId || previous.productId !== input.productId || previous.sessionId !== input.sessionId || previous.compartmentId !== input.compartmentId) {
        throw new AppError("This order reference is already in use.", 409);
      }
      return structuredClone(previous);
    }
    const robot = this.robot(input.robotId);
    if (robot.status !== "available" || this.busy.has(robot.id)) throw new AppError("Vendigo is busy right now. Please try again in a moment.", 409);
    const item = this.state.inventory.find((i) => i.robotId === robot.id && i.productId === input.productId);
    if (!item || item.compartmentId !== input.compartmentId) throw new AppError("That product and compartment do not match.");
    if (this.state.products.find((p) => p.id === input.productId)?.enabled === false) throw new AppError("That product is unavailable.", 409);
    if (item.stock < 1) throw new AppError("That item just sold out. Please choose another.", 409);
    return this.open({ id: input.orderId, robotId: robot.id, productId: input.productId, compartmentId: input.compartmentId, sessionId: input.sessionId, locationId: robot.locationId, status: "opening", closesAt: null, error: null });
  }

  private async open(order: Order) {
    const robot = this.robot(order.robotId);
    this.busy.add(robot.id);
    this.orders.set(order.id, order);
    if (robot.status !== "stopped") robot.status = "selling";
    this.publish();
    try {
      await this.hardware.unlockCompartment(robot.id, order.compartmentId);
    } catch {
      order.status = "failed";
      order.error = "We couldn’t unlock the compartment. Please try again.";
      this.busy.delete(robot.id);
      if (robot.status === "selling") robot.status = "available";
      this.publish();
      return structuredClone(order);
    }
    order.status = "unlocked";
    order.openedAt = Date.now();
    order.closesAt = order.openedAt + this.duration;
    this.scheduleClose(order.id, this.duration);
    try { this.publish(); }
    catch (error) {
      // A storage failure after opening must never release the compartment or
      // prevent its close timer. Keep the acknowledgement for the retry.
      Object.assign(this.orders.get(order.id)!, order);
      throw error;
    }
    return structuredClone(order);
  }

  async close(id: string) {
    let order = this.orders.get(id);
    if (!order || !["unlocked", "lock_failed"].includes(order.status)) return;
    order.status = "locking";
    order.error = null;
    const openedAt = order.openedAt;
    try { this.publish(); }
    catch {
      // Disk trouble must not prevent closing an already-open compartment.
      order = this.orders.get(id)!;
      order.status = "locking";
      order.openedAt = openedAt;
    }
    try {
      await this.hardware.lockCompartment(order.robotId, order.compartmentId);
    } catch {
      order.status = "lock_failed";
      order.error = "The compartment could not relock. Please ask the operator for help.";
      this.robot(order.robotId).status = "stopped";
      this.publish();
      return;
    }
    try { this.completePurchase(order); }
    catch (error) {
      const restored = this.orders.get(id)!;
      restored.status = "unlocked";
      restored.openedAt = openedAt;
      this.scheduleClose(id, 2_000);
      throw error;
    }
  }

  /** The sole completed-purchase commit: record, stock, order and metrics together. */
  private completePurchase(order: Order) {
    if (order.status === "completed") return;
    const interruptedBeforeAcknowledgement = order.productId && !order.openedAt;
    if (order.productId && !interruptedBeforeAcknowledgement && !this.state.transactions.some((t) => t.id === order.id)) {
      const item = this.state.inventory.find((i) => i.robotId === order.robotId && i.productId === order.productId);
      const product = this.state.products.find((p) => p.id === order.productId);
      if (!item || !product || item.stock < 1) throw new AppError("That item is sold out.", 409);
      this.state.transactions.unshift({ id: order.id, robotId: order.robotId, productId: product.id, productName: product.name, locationId: order.locationId, amountCents: product.priceCents, createdAt: new Date().toISOString() });
      item.stock -= 1;
      const buyer = `${order.robotId}:${order.sessionId}`;
      this.buyers.add(buyer);
      this.state.purchasingSessions = this.buyers.size;
    }
    order.status = interruptedBeforeAcknowledgement ? "failed" : "completed";
    if (interruptedBeforeAcknowledgement) order.error = "The server restarted before confirming pickup. No purchase was recorded; please choose your item again.";
    this.busy.delete(order.robotId);
    const robot = this.robot(order.robotId);
    if (robot.status === "selling") robot.status = "available";
    this.publish();
  }

  async command(robotId: string, command: RobotCommand, compartmentId?: number) {
    const robot = this.robot(robotId);
    if (command === "retry-lock") {
      const order = [...this.orders.values()].find((o) => o.robotId === robotId && o.status === "lock_failed");
      if (!order) throw new AppError("No compartment needs a lock retry.", 409);
      await this.close(order.id);
      return;
    }
    if (command === "stop") {
      // Stop takes priority over commands awaiting a hardware acknowledgement.
      this.commandVersions.set(robotId, (this.commandVersions.get(robotId) ?? 0) + 1);
      robot.status = "stopped";
      this.publish();
      await this.hardware.stopRobot(robotId);
      return;
    }
    if (this.busy.has(robotId)) throw new AppError("Wait for the open compartment to relock before moving Vendigo.", 409);
    if (command === "unlock") {
      if (robot.status === "returning") throw new AppError("Stop Vendigo before opening a compartment.", 409);
      const item = this.state.inventory.find((i) => i.robotId === robotId && i.compartmentId === compartmentId);
      if (!item) throw new AppError("Choose a valid compartment.");
      return this.open({ id: randomUUID(), robotId, productId: null, compartmentId: item.compartmentId, sessionId: "operator", locationId: robot.locationId, status: "opening", closesAt: null, error: null });
    }
    this.busy.add(robotId);
    const version = this.commandVersions.get(robotId) ?? 0;
    try {
      if (command === "resume") {
        await this.hardware.resumeRobot(robotId);
        if (version === (this.commandVersions.get(robotId) ?? 0)) robot.status = "available";
      } else if (command === "return-to-base") {
        await this.hardware.returnToBase(robotId);
        if (version === (this.commandVersions.get(robotId) ?? 0)) robot.status = "returning";
      }
      this.publish();
    } finally {
      this.busy.delete(robotId);
    }
  }

  dispose() {
    for (const timer of this.timers) clearTimeout(timer);
    this.listeners.clear();
  }
}
