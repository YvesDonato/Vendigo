"use client";

import { useEffect, useState } from "react";
import type { AppSnapshot } from "@/types";

export function useLiveState() {
  const [state, setState] = useState<AppSnapshot | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    let healthy = false;
    const accept = (snapshot: AppSnapshot) => {
      if (!active) return;
      setState((current) => !current || snapshot.startedAt !== current.startedAt || snapshot.revision >= current.revision ? snapshot : current);
      setError(false);
    };
    const poll = async () => {
      try {
        const response = await fetch("/api/state", { cache: "no-store", signal: AbortSignal.timeout(8_000) });
        if (!response.ok) throw new Error();
        accept(await response.json());
      } catch { if (active) setError(true); }
    };
    const events = new EventSource("/api/events");
    events.onmessage = (event) => {
      healthy = true;
      if (active) setConnected(true);
      accept(JSON.parse(event.data));
    };
    events.onerror = () => {
      healthy = false;
      if (active) setConnected(false);
      void poll();
    };
    void poll();
    const fallback = setInterval(() => { if (!healthy) void poll(); }, 3_000);
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
