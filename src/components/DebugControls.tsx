"use client";

import { useRouter } from "next/navigation";
import { ChevronsUp, RotateCcw } from "lucide-react";
import { useDelivery } from "@/context/DeliveryContext";

export function DebugControls() {
  const router = useRouter();
  const { request, advanceStatus, adjustQueue, reset } = useDelivery();

  if (process.env.NODE_ENV !== "development") return null;

  return (
    <details className="debug-controls">
      <summary>Demo controls</summary>
      <div className="debug-controls-inner">
        {request && (
          <>
            <button type="button" onClick={() => advanceStatus()}>
              <ChevronsUp size={15} /> Advance
            </button>
            <button type="button" onClick={() => advanceStatus("dispatched")}>Dispatch</button>
            <button type="button" onClick={() => advanceStatus("arriving")}>Arrive</button>
            <button type="button" onClick={() => adjustQueue(-1)}>Queue −</button>
            <button type="button" onClick={() => adjustQueue(1)}>Queue +</button>
          </>
        )}
        <button
          type="button"
          onClick={() => {
            reset();
            router.push("/");
          }}
        >
          <RotateCcw size={14} /> Reset demo
        </button>
      </div>
    </details>
  );
}
