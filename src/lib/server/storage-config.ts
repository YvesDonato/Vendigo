import { AppError } from "./store.ts";

export function storageMode(env: Record<string, string | undefined> = process.env): "json" | "blob" {
  const mode = env.VENDIGO_STORAGE || (env.VERCEL === "1" ? "blob" : "json");
  if (mode !== "json" && mode !== "blob") throw new AppError("VENDIGO_STORAGE must be json or blob.", 503);
  if (env.VERCEL === "1" && mode === "json") throw new AppError("Vercel needs shared Blob storage; local JSON files cannot persist here.", 503);
  if (mode === "blob" && !env.BLOB_READ_WRITE_TOKEN && !(env.BLOB_STORE_ID && env.VERCEL_OIDC_TOKEN)) {
    throw new AppError("Connect a private Vercel Blob store to this project and redeploy to enable inventory.", 503);
  }
  return mode;
}

export function blobPath(env: Record<string, string | undefined> = process.env) {
  return env.VENDIGO_BLOB_PATH || `vendigo/${env.VERCEL_ENV === "preview" ? "preview" : "production"}/state.json`;
}
