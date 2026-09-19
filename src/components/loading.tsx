import { Brand } from "./brand";
import { Radio } from "lucide-react";

export function Loading({ error = false }: { error?: boolean }) {
  return <main className="loading-screen"><Brand /><Radio size={28} className="text-blue" /><h1>{error ? "Reconnecting…" : "Loading…"}</h1>{error && <p>Check your connection. We’ll reconnect automatically.</p>}</main>;
}
