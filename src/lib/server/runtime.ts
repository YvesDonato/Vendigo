import { DemoStore } from "./store";
import { JsonStateStorage } from "./storage";
import { resolve } from "node:path";

const globalStore = globalThis as typeof globalThis & { hawk2uStore?: DemoStore };
// One Node process serves all route handlers and browsers, including after HMR.
export const store = globalStore.hawk2uStore ??= new DemoStore(undefined, undefined,
  new JsonStateStorage(resolve(/* turbopackIgnore: true */ process.env.VENDIGO_DATA_FILE || "data/state.json")));
