"use client";

import { useEffect, useState } from "react";
import type { AppSnapshot } from "@/types";

export function useLiveState() {
  const [state, setState] = useState<AppSnapshot | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    let polling = false;
    const accept = (snapshot: AppSnapshot) => {
      if (!active) return;
      setState((current) => !current || snapshot.serverInstanceId !== current.serverInstanceId || snapshot.startedAt !== current.startedAt || snapshot.revision >= current.revision ? snapshot : current);
      setError(false);
    };
    const poll = async () => {
      if (polling || !active) return;
      polling = true;
      try {
        const response = await fetch("/api/state", { cache: "no-store", signal: AbortSignal.timeout(8_000) });
        if (!response.ok) throw new Error();
        accept(await response.json());
      } catch { if (active) setError(true); }
      finally { polling = false; }
    };
    const events = new EventSource("/api/events");
    events.onmessage = (event) => {
      if (active) setConnected(true);
      accept(JSON.parse(event.data));
    };
    events.onerror = () => {
      if (active) setConnected(false);
      void poll();
    };
    void poll();
    // Also catches direct inventory.json edits, which have no browser mutation event.
    const fallback = setInterval(() => { void poll(); }, 1_000);
    const onVisible = () => { if (document.visibilityState === "visible") void poll(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      events.close();
      clearInterval(fallback);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  return { state, connected, error };
}
