"use client";

import { useRouter } from "next/navigation";
import { ArrowRight, Zap } from "lucide-react";
import { DebugControls } from "@/components/DebugControls";
import { Header } from "@/components/Header";
import { ItemGrid } from "@/components/ItemGrid";
import { useDelivery } from "@/context/DeliveryContext";
import { items } from "@/data/items";

export default function CatalogPage() {
  const router = useRouter();
  const { draft, setItemQuantity, hydrated, request } = useDelivery();

  function selectSnack(itemId: string) {
    if (!hydrated) return;
    Object.keys(draft.selections).forEach((selectedId) => {
      if (selectedId !== itemId) setItemQuantity(selectedId, 0);
    });
    setItemQuantity(itemId, 1);
    router.push("/location");
  }

  return (
    <main className="app-shell">
      <Header />
      <div className="page-content catalog-page">
        <section className="page-intro catalog-intro">
          <h1>Pick a snack</h1>
        </section>

        {request && request.status !== "delivered" && (
          <button className="active-request-banner" onClick={() => router.push("/tracking")}>
            <span className="active-request-icon"><Zap size={16} fill="currentColor" /></span>
            <span><strong>Active request</strong></span>
            <ArrowRight size={18} aria-hidden="true" />
          </button>
        )}

        <ItemGrid
          items={items}
          selections={draft.selections}
          onQuantityChange={(itemId) => selectSnack(itemId)}
        />
      </div>
      <DebugControls />
    </main>
  );
}
