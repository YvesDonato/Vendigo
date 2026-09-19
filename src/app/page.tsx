"use client";

import { useRouter } from "next/navigation";
import { ArrowRight, Zap } from "lucide-react";
import { BottomActionBar } from "@/components/BottomActionBar";
import { DebugControls } from "@/components/DebugControls";
import { Header } from "@/components/Header";
import { ItemGrid } from "@/components/ItemGrid";
import { useDelivery } from "@/context/DeliveryContext";
import { items } from "@/data/items";

export default function CatalogPage() {
  const router = useRouter();
  const { draft, itemCount, setItemQuantity, hydrated, request } = useDelivery();

  return (
    <main className="app-shell has-bottom-action">
      <Header />
      <div className="page-content catalog-page">
        <section className="page-intro catalog-intro">
          <div className="system-status"><span /> Vehicle ready</div>
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
          onQuantityChange={setItemQuantity}
        />
      </div>

      <BottomActionBar
        label="Continue"
        onClick={() => router.push("/location")}
        disabled={!hydrated || itemCount === 0}
      />
      <DebugControls />
    </main>
  );
}
