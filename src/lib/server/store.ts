import { randomUUID } from "node:crypto";
import { createSeed } from "../demo-data.ts";
import { robotHardware, type RobotHardware } from "../robot/hardware.ts";
import type { AppSnapshot, Order, RobotCommand } from "../../types/index.ts";

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

  constructor(hardware = robotHardware, unlockDurationMs = 7_000) {
    this.hardware = hardware;
    this.duration = unlockDurationMs;
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
    if (item.stock < 1) throw new AppError("That item just sold out. Please choose another.", 409);
    this.scan(robot.id, input.sessionId);
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
      order.status = "unlocked";
      order.closesAt = Date.now() + this.duration;
      const timer = setTimeout(() => {
        this.timers.delete(timer);
        void this.close(order.id);
      }, this.duration);
      timer.unref?.();
      this.timers.add(timer);
      this.publish();
    } catch {
      order.status = "failed";
      order.error = "We couldn’t unlock the compartment. Please try again.";
      this.busy.delete(robot.id);
      if (robot.status === "selling") robot.status = "available";
      this.publish();
    }
    return structuredClone(order);
  }

  async close(id: string) {
    const order = this.orders.get(id);
    if (!order || !["unlocked", "lock_failed"].includes(order.status)) return;
    order.status = "locking";
    order.error = null;
    this.publish();
    try {
      await this.hardware.lockCompartment(order.robotId, order.compartmentId);
      if (order.productId) {
        const item = this.state.inventory.find((i) => i.robotId === order.robotId && i.productId === order.productId)!;
        const product = this.state.products.find((p) => p.id === order.productId)!;
        item.stock -= 1;
        this.state.transactions.unshift({ id: order.id, robotId: order.robotId, productId: order.productId, locationId: order.locationId, amountCents: product.priceCents, createdAt: new Date().toISOString() });
        const buyer = `${order.robotId}:${order.sessionId}`;
        if (!this.buyers.has(buyer)) {
          this.buyers.add(buyer);
          this.state.purchasingSessions += 1;
        }
      }
      order.status = "completed";
      this.busy.delete(order.robotId);
      const robot = this.robot(order.robotId);
      if (robot.status === "selling") robot.status = "available";
    } catch {
      order.status = "lock_failed";
      order.error = "The compartment could not relock. Please ask the operator for help.";
      this.robot(order.robotId).status = "stopped";
    }
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
