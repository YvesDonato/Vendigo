"use client";

import Image from "next/image";
import { useState } from "react";
import { api } from "@/lib/client";
import type { AppSnapshot } from "@/types";

export function InventoryPanel({ state }: { state: AppSnapshot }) {
  const [drafts, setDrafts] = useState<Record<string, { value: string; expectedStock: number }>>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const robotId = state.robots[0].id;
  const inventory = state.inventory.filter((item) => item.robotId === robotId);
  const stock = inventory.reduce((sum, item) => sum + item.stock, 0);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true); setError(""); setMessage("");
    try {
      const items = Object.entries(drafts).map(([productId, draft]) => ({ productId, stock: Number(draft.value), expectedStock: draft.expectedStock }));
      await api("/api/inventory", { robotId, items });
      setDrafts({}); setMessage("Inventory saved.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not save inventory."); }
    finally { setSaving(false); }
  }

  return <section className="panel inventory-panel" id="inventory">
    <div className="panel-heading"><h2>Inventory</h2></div>
    <p className="inventory-summary">Total Items Remaining: <strong data-testid="inventory-total">{stock}</strong></p>
    <form onSubmit={save}>
      <div className="inventory-list">{inventory.map((item) => {
        const product = state.products.find((p) => p.id === item.productId)!;
        return <div className="inventory-row" key={item.productId} data-testid={`inventory-${item.productId}`}>
          <div className="inventory-image"><Image src={product.image} width={32} height={44} alt="" /></div>
          <label className="inventory-label" htmlFor={`quantity-${item.productId}`}>{product.name}</label>
          <input id={`quantity-${item.productId}`} className="inventory-quantity" type="number" min="0" max={Number.MAX_SAFE_INTEGER} step="1" required disabled={saving}
            value={drafts[item.productId]?.value ?? item.stock}
            onChange={(event) => {
              setMessage("");
              setDrafts((current) => ({ ...current, [item.productId]: { value: event.target.value, expectedStock: current[item.productId]?.expectedStock ?? item.stock } }));
            }} />
        </div>;
      })}</div>
      <div className="inventory-actions">
        <button className="button button-primary" disabled={saving || !Object.keys(drafts).length}>{saving ? "Saving…" : "Save Inventory"}</button>
        {Object.keys(drafts).length > 0 && <button className="button button-secondary" type="button" disabled={saving} onClick={() => { setDrafts({}); setError(""); }}>Reload saved quantities</button>}
        {message && <p role="status">{message}</p>}
        {error && <p className="inline-error" role="alert">{error}</p>}
      </div>
    </form>
  </section>;
}
