import { DemoStore } from "./store";
import { JsonStateStorage } from "./storage";
import { dirname, join, resolve } from "node:path";
import { BlobStore } from "./blob-store";
import { BlobStateStorage } from "./blob-storage";
import { blobPath, storageMode } from "./storage-config";

const globalStore = globalThis as typeof globalThis & { vendigoJsonStore?: DemoStore; vendigoBlobStore?: BlobStore };
// Initialize only inside a request. Next's parallel build workers must never
// create data, import legacy state, or resume a hardware pickup during a build.
export function getStore() {
  if (storageMode() === "blob") {
    return globalStore.vendigoBlobStore ??= new BlobStore(new BlobStateStorage(blobPath()));
  }
  const directory = resolve(/* turbopackIgnore: true */ process.env.VENDIGO_DATA_DIR || (process.env.VENDIGO_DATA_FILE ? dirname(process.env.VENDIGO_DATA_FILE) : "data"));
  const legacyPath = resolve(/* turbopackIgnore: true */ process.env.VENDIGO_DATA_FILE || join(directory, "state.json"));
  return globalStore.vendigoJsonStore ??= new DemoStore(undefined, undefined,
    new JsonStateStorage(directory, legacyPath));
}
