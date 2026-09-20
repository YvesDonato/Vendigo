import { existsSync, renameSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { isDeepStrictEqual } from "node:util";
import type { AppSnapshot, Order } from "../../types/index.ts";
import { InventoryStore, validateInventory, type InventoryDocument } from "./inventory-store.ts";
import { PurchaseStore, validatePurchases, type PurchaseDocument } from "./purchase-store.ts";
import { AnalyticsStore, validateAnalytics, type AnalyticsDocument } from "./analytics-store.ts";
import { object, readJson, writeJson } from "./json-file.ts";

export interface StoredState {
  version: 1;
  state: AppSnapshot;
  orders: Order[];
  sessions: string[];
  buyers: string[];
}
export interface StateStorage {
  load(): StoredState | null;
  save(data: StoredState): void;
}
interface Documents {
  inventory: InventoryDocument;
  purchases: PurchaseDocument;
  analytics: AnalyticsDocument;
}

function validateDocuments(value: unknown): asserts value is Documents {
  if (!object(value)) throw new Error("Invalid storage transaction.");
  validateInventory(value.inventory); validatePurchases(value.purchases); validateAnalytics(value.analytics);
}

/** Three authoritative documents with a small recovery journal for multi-file commits.
 * One Node process owns writes. No database and no long-lived inventory cache.
 */
export class JsonStateStorage implements StateStorage {
  readonly inventory: InventoryStore;
  readonly purchases: PurchaseStore;
  readonly analytics: AnalyticsStore;
  readonly journalPath: string;
  readonly legacyPath: string;
  private initialized = false;

  constructor(directory: string, legacyPath = join(directory, "state.json")) {
    this.inventory = new InventoryStore(join(directory, "inventory.json"));
    this.purchases = new PurchaseStore(join(directory, "purchases.json"));
    this.analytics = new AnalyticsStore(join(directory, "analytics.json"));
    this.journalPath = join(directory, ".pending-transaction.json");
    this.legacyPath = legacyPath;
  }

  private apply(documents: Documents) {
    this.inventory.write(documents.inventory);
    this.purchases.write(documents.purchases);
    this.analytics.write(documents.analytics);
    unlinkSync(this.journalPath);
  }

  private recover() {
    if (!existsSync(this.journalPath)) return;
    const documents = readJson(this.journalPath);
    validateDocuments(documents);
    this.apply(documents);
  }

  load(): StoredState | null {
    this.recover();
    const paths = [this.inventory.path, this.purchases.path, this.analytics.path];
    if (!paths.some(existsSync)) {
      if (this.initialized) throw new Error("Vendigo data files are missing; restore them instead of resetting the store.");
      if (!existsSync(this.legacyPath)) return null;
      // Preserve prior demo data once; the old file is never an active source again.
      const legacy = readJson(this.legacyPath) as StoredState;
      if (legacy?.version !== 1 || !legacy.state || !Array.isArray(legacy.orders) || !Array.isArray(legacy.sessions) || !Array.isArray(legacy.buyers)) throw new Error("Invalid legacy state.json.");
      this.save(legacy);
      renameSync(this.legacyPath, `${this.legacyPath}.bak`);
    }
    if (!paths.every(existsSync)) throw new Error("A Vendigo JSON file is missing; restore the missing file.");
    const inventory = this.inventory.read();
    const purchases = this.purchases.read();
    const analytics = this.analytics.read();
    this.initialized = true;
    return {
      version: 1,
      state: {
        revision: analytics.revision, startedAt: analytics.started_at, robots: analytics.robots,
        ...InventoryStore.toSnapshot(inventory), locations: analytics.locations,
        transactions: PurchaseStore.toTransactions(purchases), activeOrders: [],
        qrScans: analytics.qr_scans, purchasingSessions: analytics.buyer_ids.length,
      },
      orders: purchases.orders, sessions: analytics.visit_ids, buyers: analytics.buyer_ids,
    };
  }

  save(data: StoredState) {
    this.recover();
    const documents: Documents = {
      inventory: InventoryStore.fromSnapshot(data.state.products, data.state.inventory),
      purchases: {
        purchases: data.state.transactions.map((p) => ({ order_id: p.id, product_id: p.productId,
          product_name: p.productName ?? data.state.products.find((product) => product.id === p.productId)?.name ?? p.productId,
          price: p.amountCents / 100, timestamp: p.createdAt, robot_id: p.robotId, location_id: p.locationId })),
        orders: data.orders,
      },
      analytics: { qr_scans: data.state.qrScans, visit_ids: data.sessions, buyer_ids: data.buyers,
        revision: data.state.revision, started_at: data.state.startedAt, robots: data.state.robots, locations: data.state.locations },
    };
    validateDocuments(documents);
    // The journal is the commit decision. Interrupted replacements are replayed
    // before any subsequent read, so a purchase cannot leave stock half-updated.
    writeJson(this.journalPath, documents);
    this.apply(documents);
    this.initialized = true;
  }
}

export const sameStoredState = (a: StoredState, b: StoredState) => isDeepStrictEqual(a, b);
