import { Brand } from "./brand";
import { Radio } from "lucide-react";

export function Loading({ error = false }: { error?: boolean }) {
  return <main className="loading-screen"><Brand /><div className="loading-orbit"><Radio size={30} /></div><h1>{error ? "Reconnecting to Hawk" : "Getting things ready"}</h1><p>{error ? "Check your connection. We’ll reconnect automatically." : "Your storefront is just a moment away."}</p></main>;
}
