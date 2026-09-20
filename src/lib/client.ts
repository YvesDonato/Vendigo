export async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(12_000),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? "Unable to reach Vendigo. Please try again.");
  return data as T;
}

export function sessionValue(key: string, fallback: string) {
  try {
    const value = sessionStorage.getItem(key) ?? fallback;
    sessionStorage.setItem(key, value);
    return value;
  } catch { return fallback; }
}

export function saveSession(key: string, value: string | null) {
  try {
    if (value === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, value);
  } catch { /* A storage-restricted browser can still complete a purchase. */ }
}

// Works on plain HTTP LAN origins too, where crypto.randomUUID may be unavailable.
export function newId() {
  return globalThis.crypto?.randomUUID?.() ?? `hawk-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
