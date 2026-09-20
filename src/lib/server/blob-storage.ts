import { BlobPreconditionFailedError, get, put } from "@vercel/blob";
import { setTimeout as delay } from "node:timers/promises";
import { createSeed } from "../demo-data.ts";
import { object } from "./json-file.ts";
import { AppError } from "./store.ts";
import { fromDocuments, toDocuments, validateDocuments, type StoredState } from "./storage.ts";

export class StorageConflict extends Error {}

/** Injectable transport; tests run independent server instances against one object. */
export interface JsonObjectClient {
  read(path: string): Promise<{ value: unknown; etag: string } | null>;
  write(path: string, value: unknown, etag: string | null): Promise<void>;
}

export const vercelObjectClient: JsonObjectClient = {
  async read(path) {
    // CDN-cached Blob reads can be stale. Always read the origin for retail facts.
    const result = await get(path, { access: "private", useCache: false,
      // Compression can turn the version into a weak W/ ETag. Conditional
      // writes require the strong tag for the original stored representation.
      headers: { "Accept-Encoding": "identity" }, abortSignal: AbortSignal.timeout(8_000) });
    if (!result) return null;
    if (result.statusCode !== 200 || !result.stream || !result.blob.etag) throw new Error("Inventory storage did not return current data.");
    if (result.blob.etag.startsWith("W/")) throw new AppError("Shared inventory storage returned a weak version tag. Please retry.", 503);
    return { value: await new Response(result.stream).json(), etag: result.blob.etag };
  },
  async write(path, value, etag) {
    try {
      await put(path, JSON.stringify(value), {
        access: "private", contentType: "application/json", addRandomSuffix: false,
        abortSignal: AbortSignal.timeout(8_000),
        // Creating a fresh store must never overwrite another cold start's data.
        allowOverwrite: etag !== null, ...(etag === null ? {} : { ifMatch: etag }),
      });
    } catch (error) {
      if (error instanceof BlobPreconditionFailedError || (etag === null && error instanceof Error && /already exists/i.test(error.message))) {
        throw new StorageConflict("Inventory changed during this request.");
      }
      throw error;
    }
  },
};

/** One private JSON object atomically contains all three retail documents. */
export class BlobStateStorage {
  readonly path: string;
  private client: JsonObjectClient;
  constructor(path: string, client: JsonObjectClient = vercelObjectClient) {
    this.path = path; this.client = client;
  }

  async read() {
    for (let attempt = 0; attempt < 10; attempt++) {
      const current = await this.client.read(this.path);
      if (current) {
        if (!object(current.value) || current.value.version !== 1) throw new Error("Unsupported Vendigo Blob state.");
        validateDocuments(current.value);
        return { data: fromDocuments(current.value), etag: current.etag };
      }
      const data: StoredState = { version: 1, state: createSeed(), orders: [], sessions: [], buyers: [] };
      try { await this.client.write(this.path, { version: 1, ...toDocuments(data) }, null); }
      catch (error) { if (!(error instanceof StorageConflict)) throw error; }
    }
    throw new Error("Could not initialize shared Vendigo storage.");
  }

  async update<T>(change: (data: StoredState) => T): Promise<T> {
    for (let attempt = 0; attempt < 10; attempt++) {
      const current = await this.read();
      const next = structuredClone(current.data);
      // This callback must contain only state changes, never hardware/network IO.
      const result = change(next);
      if (JSON.stringify(next) === JSON.stringify(current.data)) return result;
      try {
        await this.client.write(this.path, { version: 1, ...toDocuments(next) }, current.etag);
        return result;
      } catch (error) {
        if (!(error instanceof StorageConflict)) throw error;
        await delay(10 + Math.random() * 30);
      }
    }
    throw new AppError("Inventory changed repeatedly while saving. Please retry the request.", 409);
  }
}
