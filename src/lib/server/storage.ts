import { closeSync, existsSync, fsyncSync, mkdirSync, openSync, readFileSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { randomUUID } from "node:crypto";
import type { AppSnapshot, Order } from "../../types/index.ts";

export interface StoredState {
  version: 1;
  state: AppSnapshot;
  orders: Order[];
  sessions: string[];
  buyers: string[];
}

/** One replaceable persistence boundary; the application is the single writer. */
export interface StateStorage {
  load(): StoredState | null;
  save(data: StoredState): void;
}

export class JsonStateStorage implements StateStorage {
  readonly path: string;
  constructor(path: string) { this.path = path; }

  load(): StoredState | null {
    if (!existsSync(this.path)) return null;
    const data = JSON.parse(readFileSync(this.path, "utf8")) as StoredState;
    // Fail closed instead of resetting corrupt data to a fresh catalog.
    if (data.version !== 1 || !Array.isArray(data.orders) || !Array.isArray(data.sessions) || !Array.isArray(data.buyers) ||
        !Array.isArray(data.state?.inventory) || !Array.isArray(data.state.products) || !Array.isArray(data.state.transactions) ||
        !Number.isSafeInteger(data.state.qrScans) || data.state.qrScans < 0 ||
        data.state.inventory.some((i) => !Number.isSafeInteger(i.stock) || i.stock < 0) ||
        data.state.products.some((p) => !Number.isSafeInteger(p.priceCents) || p.priceCents < 0)) {
      throw new Error(`Invalid Vendigo state at ${this.path}; restore a valid backup.`);
    }
    return data;
  }

  save(data: StoredState) {
    mkdirSync(dirname(this.path), { recursive: true });
    const temporary = `${this.path}.${randomUUID()}.tmp`;
    try {
      const fd = openSync(temporary, "wx", 0o600);
      try {
        writeFileSync(fd, JSON.stringify(data, null, 2) + "\n");
        fsyncSync(fd);
      } finally { closeSync(fd); }
      // Same-directory atomic replacement keeps purchases and stock in one commit.
      renameSync(temporary, this.path);
    } finally {
      if (existsSync(temporary)) unlinkSync(temporary);
    }
  }
}
