"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, Check } from "lucide-react";
import { Brand } from "@/components/brand";
import { Loading } from "@/components/loading";
import { useLiveState } from "@/hooks/use-live-state";
import { api, newId, saveSession, sessionValue } from "@/lib/client";
import { priceLabel } from "@/lib/format";
import { Purchase } from "./purchase";
import type { Order, Product } from "@/types";

export function Storefront({ robotId }: { robotId: string }) {
  const { state, error } = useLiveState();
  const [category, setCategory] = useState<"all" | "drinks" | "snacks">("all");
  const [selected, setSelected] = useState<Product | null>(null);
  const [restored, setRestored] = useState<Order>();
  const [notice, setNotice] = useState("");
  const sessionId = useRef("");
  const recovered = useRef(false);

  useEffect(() => {
    sessionId.current = sessionValue(`hawk-session-${robotId}`, newId());
    void api("/api/scans", { robotId, sessionId: sessionId.current }).catch(() => {});
  }, [robotId]);

  useEffect(() => {
    if (!state || recovered.current) return;
    recovered.current = true;
    const stored = sessionValue(`hawk-order-${robotId}`, "");
    if (!stored) return;
    try {
      const { orderId, productId } = JSON.parse(stored);
      void api<Order>(`/api/orders/${orderId}`).then((order) => {
        if (["completed", "failed"].includes(order.status)) { saveSession(`hawk-order-${robotId}`, null); return; }
        const product = state.products.find((p) => p.id === productId);
        if (product) { setRestored(order); setSelected(product); }
      }).catch(() => {});
    } catch { saveSession(`hawk-order-${robotId}`, null); }
  }, [state, robotId]);

  const completed = useCallback(() => {
    setSelected(null);
    setRestored(undefined);
    setNotice("Pickup complete. Enjoy!");
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 5_000);
    return () => clearTimeout(timer);
  }, [notice]);

  if (!state) return <Loading error={error} />;
  const robot = state.robots.find((r) => r.id === robotId);
  if (!robot) return <main className="loading-screen"><Brand /><h1>Storefront not found</h1><p>Check the QR code and try again.</p><Link className="button button-primary" href="/shop/robot-001">Open storefront <ArrowRight size={17} /></Link></main>;
  const inventory = state.inventory.filter((i) => i.robotId === robotId);
  const available = robot.status === "available" && !error;
  const unavailableReason = robot.status === "selling" ? "Pickup in progress. Please wait a moment." : robot.status === "returning" ? "Vendigo is returning to base. Purchases are paused." : robot.status === "stopped" ? "Purchases are paused by the operator." : null;

  return <div className="storefront">
    <header className="shop-header"><Brand href={`/shop/${robotId}`} /></header>
    <main>
      <section className="shop-hero">
        <h1>Drinks & snacks.</h1>
        <p>Pick an item. Tap to unlock.</p>
      </section>
      {error && <div className="connection-banner" role="status">Connection lost. Reconnecting to Vendigo…</div>}
      {!error && unavailableReason && !selected && <div className="connection-banner" role="status">{unavailableReason}</div>}
      <section className="shop-products" id="products" aria-label="Products">
        <div className="product-tabs" aria-label="Product categories">{(["all", "drinks", "snacks"] as const).map((tab) => <button key={tab} aria-pressed={category === tab} className={category === tab ? "active" : ""} onClick={() => setCategory(tab)}>{tab === "all" ? "All" : tab === "drinks" ? "Drinks" : "Snacks"}</button>)}</div>
        <div className="product-grid">{state.products.filter((p) => category === "all" || p.category === category).map((product) => {
          const item = inventory.find((i) => i.productId === product.id)!;
          return <article className="product-card" key={product.id} data-testid={`product-${product.id}`}>
            <div className="product-image"><Image src={product.image} alt={`${product.name} product illustration`} width={240} height={300} priority={product.id === "coke"} /></div>
            <div className="product-details">
              <h2>{product.name}</h2>
              <div className="product-meta"><strong>{priceLabel(product.priceCents)}</strong><span className={item.stock <= 4 ? "text-amber" : ""}>{item.stock === 0 ? "Sold out" : `${item.stock} left`}</span></div>
              <button className="button get-item" disabled={!available || item.stock === 0} onClick={() => { setRestored(undefined); setSelected(product); }}>{item.stock === 0 ? "Sold out" : "Get Item"}</button>
            </div>
          </article>;
        })}</div>
      </section>
    </main>
    <footer className="shop-footer"><Link href="/dashboard">Dashboard <ArrowRight size={14} /></Link></footer>
    {notice && <div className="toast" role="status"><Check size={18} /> {notice}</div>}
    {selected && <Purchase product={selected} inventory={inventory.find((i) => i.productId === selected.id)!} getSessionId={() => sessionId.current} initialOrder={restored} onClose={() => { setSelected(null); setRestored(undefined); }} onComplete={completed} />}
  </div>;
}
