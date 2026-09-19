import { DemoStore } from "./store";

const globalStore = globalThis as typeof globalThis & { hawk2uStore?: DemoStore };
// One Node process serves all route handlers and browsers, including after HMR.
export const store = globalStore.hawk2uStore ??= new DemoStore();
