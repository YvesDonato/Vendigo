import { moneyCents, object, readJson, writeJson } from "./json-file.ts";
import type { Order, Transaction } from "../../types/index.ts";

export interface PurchaseRecord {
  order_id: string;
  product_id: string;
  product_name: string;
  price: number;
  timestamp: string;
  robot_id: string;
  location_id: string;
}
export interface PurchaseDocument { purchases: PurchaseRecord[]; orders: Order[] }

export function validatePurchases(value: unknown): asserts value is PurchaseDocument {
  if (!object(value) || !Array.isArray(value.purchases) || !Array.isArray(value.orders)) throw new Error("Invalid purchases.json.");
  const ids = new Set<string>();
  for (const purchase of value.purchases) {
    if (!object(purchase) || typeof purchase.order_id !== "string" || !purchase.order_id || ids.has(purchase.order_id) ||
        typeof purchase.product_id !== "string" || typeof purchase.product_name !== "string" ||
        typeof purchase.robot_id !== "string" || typeof purchase.location_id !== "string" ||
        typeof purchase.timestamp !== "string" || !Number.isFinite(Date.parse(purchase.timestamp))) throw new Error("Invalid or duplicate purchase record.");
    moneyCents(purchase.price);
    ids.add(purchase.order_id);
  }
  const orderIds = new Set<string>();
  for (const order of value.orders) {
    if (!object(order) || typeof order.id !== "string" || orderIds.has(order.id) ||
        typeof order.robotId !== "string" || typeof order.sessionId !== "string" ||
        !["opening", "unlocked", "locking", "completed", "failed", "lock_failed"].includes(String(order.status))) throw new Error("Invalid saved order.");
    orderIds.add(order.id);
  }
}

export class PurchaseStore {
  readonly path: string;
  constructor(path: string) { this.path = path; }
  read(): PurchaseDocument { const value = readJson(this.path); validatePurchases(value); return value; }
  write(value: PurchaseDocument) { validatePurchases(value); writeJson(this.path, value); }
  getRecent(limit = 20) { return this.read().purchases.sort((a, b) => b.timestamp.localeCompare(a.timestamp)).slice(0, limit); }
  static toTransactions(document: PurchaseDocument): Transaction[] {
    return document.purchases.map((p) => ({ id: p.order_id, productId: p.product_id, productName: p.product_name,
      amountCents: moneyCents(p.price), createdAt: p.timestamp, robotId: p.robot_id, locationId: p.location_id }))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }
}
