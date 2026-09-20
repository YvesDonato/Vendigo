import type { AppSnapshot } from "../types/index.ts";

/** Also used by the standalone legacy voice server: never create another store. */
export async function getLiveInventory(signal?: AbortSignal) {
  const base = process.env.VENDIGO_APP_URL || "http://127.0.0.1:3000";
  const response = await fetch(`${base.replace(/\/$/, "")}/api/state`, {
    cache: "no-store", signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(5_000)]) : AbortSignal.timeout(5_000),
  });
  if (!response.ok) throw new Error("Inventory unavailable");
  const state: AppSnapshot = await response.json();
  return state.inventory.filter((item) => item.robotId === "robot-001").map((item) => {
    const product = state.products.find((p) => p.id === item.productId);
    if (!product || !Number.isSafeInteger(item.stock) || item.stock < 0 || !Number.isSafeInteger(product.priceCents) || product.priceCents < 0) throw new Error("Invalid inventory");
    return { id: product.id, name: product.name, priceCents: product.priceCents, quantity: item.stock, available: product.enabled !== false && item.stock > 0 };
  });
}
