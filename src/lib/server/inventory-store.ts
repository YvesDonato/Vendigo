import { moneyCents, nonnegativeInteger, object, readJson, writeJson } from "./json-file.ts";
import type { InventoryItem, Product } from "../../types/index.ts";

export interface InventoryProduct extends Omit<Product, "priceCents" | "enabled"> {
  price: number;
  inventory: number;
  enabled: boolean;
  robotId: string;
  compartmentId: number;
  capacity: number;
}

export interface InventoryDocument { products: InventoryProduct[] }

export function validateInventory(value: unknown): asserts value is InventoryDocument {
  if (!object(value) || !Array.isArray(value.products)) throw new Error("inventory.json must contain a products array.");
  const ids = new Set<string>();
  const compartments = new Set<string>();
  for (const product of value.products) {
    if (!object(product) || typeof product.id !== "string" || !/^[a-zA-Z0-9_-]{1,100}$/.test(product.id) || ids.has(product.id) ||
        typeof product.name !== "string" || !product.name.trim() || typeof product.description !== "string" ||
        typeof product.image !== "string" || !product.image.startsWith("/") || typeof product.color !== "string" ||
        !["drinks", "snacks"].includes(String(product.category)) || typeof product.enabled !== "boolean" ||
        !nonnegativeInteger(product.inventory) || typeof product.robotId !== "string" || !product.robotId ||
        !nonnegativeInteger(product.compartmentId) || product.compartmentId < 1 || !nonnegativeInteger(product.capacity)) {
      throw new Error("Invalid inventory product. IDs must be unique; stock must be a nonnegative integer.");
    }
    moneyCents(product.price);
    const compartment = `${product.robotId}:${product.compartmentId}`;
    if (compartments.has(compartment)) throw new Error("Inventory compartment mappings must be unique.");
    ids.add(product.id); compartments.add(compartment);
  }
}

/** Read fresh on every query. Writes are coordinated with purchases by JsonStateStorage. */
export class InventoryStore {
  readonly path: string;
  constructor(path: string) { this.path = path; }
  read(): InventoryDocument {
    const value = readJson(this.path);
    validateInventory(value);
    return value;
  }
  write(value: InventoryDocument) { validateInventory(value); writeJson(this.path, value); }
  getProducts() { return this.read().products; }
  getProduct(idOrName: string) {
    const key = idOrName.trim().toLowerCase();
    const product = this.getProducts().find((p) => p.id.toLowerCase() === key || p.name.toLowerCase() === key);
    if (!product) throw new Error(`Unknown product: ${idOrName}`);
    return product;
  }
  getAvailableProducts() { return this.getProducts().filter((p) => p.enabled && p.inventory > 0); }

  static fromSnapshot(products: Product[], inventory: InventoryItem[]): InventoryDocument {
    return { products: products.map(({ priceCents, ...product }) => {
      const item = inventory.find((i) => i.productId === product.id);
      if (!item) throw new Error(`Missing inventory for ${product.id}`);
      return { ...product, price: priceCents / 100, inventory: item.stock, enabled: product.enabled !== false,
        robotId: item.robotId, compartmentId: item.compartmentId, capacity: item.capacity };
    }) };
  }

  static toSnapshot(document: InventoryDocument): { products: Product[]; inventory: InventoryItem[] } {
    return {
      products: document.products.map((p) => ({ id: p.id, name: p.name, description: p.description,
        image: p.image, color: p.color, category: p.category, enabled: p.enabled, priceCents: moneyCents(p.price) })),
      inventory: document.products.map((p) => ({ robotId: p.robotId, productId: p.id, compartmentId: p.compartmentId, stock: p.inventory, capacity: p.capacity })),
    };
  }
}
