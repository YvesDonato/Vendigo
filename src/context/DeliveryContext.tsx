"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { getNextStatus } from "@/lib/mockDelivery";
import type {
  DeliveryRequest,
  DeliveryStatus,
  DraftRequest,
} from "@/lib/types";

const STORAGE_KEY = "autodash-state-v1";
const emptyDraft: DraftRequest = {
  selections: {},
  locationId: null,
  locationLabel: "",
};

type PersistedState = {
  draft: DraftRequest;
  request: DeliveryRequest | null;
};

type DeliveryContextValue = PersistedState & {
  hydrated: boolean;
  itemCount: number;
  setItemQuantity: (itemId: string, quantity: number) => void;
  setLocation: (locationId: string, locationLabel: string) => void;
  setRequest: (request: DeliveryRequest) => void;
  advanceStatus: (status?: DeliveryStatus) => void;
  adjustQueue: (delta: number) => void;
  reset: () => void;
};

const DeliveryContext = createContext<DeliveryContextValue | null>(null);

export function DeliveryProvider({ children }: { children: ReactNode }) {
  const [draft, setDraft] = useState<DraftRequest>(emptyDraft);
  const [request, setRequestState] = useState<DeliveryRequest | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored) as PersistedState;
        setDraft(parsed.draft ?? emptyDraft);
        setRequestState(parsed.request ?? null);
      }
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    } finally {
      setHydrated(true);
    }
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ draft, request }));
  }, [draft, request, hydrated]);

  const setItemQuantity = useCallback((itemId: string, quantity: number) => {
    setDraft((current) => {
      const selections = { ...current.selections };
      if (quantity <= 0) delete selections[itemId];
      else selections[itemId] = quantity;
      return { ...current, selections };
    });
  }, []);

  const setLocation = useCallback((locationId: string, locationLabel: string) => {
    setDraft((current) => ({ ...current, locationId, locationLabel }));
  }, []);

  const setRequest = useCallback((nextRequest: DeliveryRequest) => {
    setRequestState(nextRequest);
  }, []);

  const advanceStatus = useCallback((status?: DeliveryStatus) => {
    setRequestState((current) => {
      if (!current) return current;
      const nextStatus = status ?? getNextStatus(current.status);
      const queuePosition =
        nextStatus === "queued" ? current.queuePosition : undefined;
      const etaByStatus: Record<DeliveryStatus, number> = {
        queued: 8,
        accepted: 7,
        preparing: 6,
        dispatched: 4,
        arriving: 1,
        delivered: 0,
      };
      return {
        ...current,
        status: nextStatus,
        queuePosition,
        etaMinutes: etaByStatus[nextStatus],
        statusUpdatedAt: new Date().toISOString(),
      };
    });
  }, []);

  const adjustQueue = useCallback((delta: number) => {
    setRequestState((current) =>
      current
        ? {
            ...current,
            queuePosition: Math.max(1, (current.queuePosition ?? 1) + delta),
          }
        : current,
    );
  }, []);

  const reset = useCallback(() => {
    setDraft(emptyDraft);
    setRequestState(null);
    window.localStorage.removeItem(STORAGE_KEY);
  }, []);

  const itemCount = Object.values(draft.selections).reduce(
    (total, quantity) => total + quantity,
    0,
  );

  const value = useMemo(
    () => ({
      draft,
      request,
      hydrated,
      itemCount,
      setItemQuantity,
      setLocation,
      setRequest,
      advanceStatus,
      adjustQueue,
      reset,
    }),
    [
      draft,
      request,
      hydrated,
      itemCount,
      setItemQuantity,
      setLocation,
      setRequest,
      advanceStatus,
      adjustQueue,
      reset,
    ],
  );

  return (
    <DeliveryContext.Provider value={value}>{children}</DeliveryContext.Provider>
  );
}

export function useDelivery() {
  const context = useContext(DeliveryContext);
  if (!context) throw new Error("useDelivery must be used within DeliveryProvider");
  return context;
}
