"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowRight, Check, ChevronRight, Leaf, MapPin, Radio, ShoppingBag, Snowflake, Sparkles } from "lucide-react";
import { Brand } from "@/components/brand";
import { Loading } from "@/components/loading";
import { useLiveState } from "@/hooks/use-live-state";
import { api, newId, saveSession, sessionValue } from "@/lib/client";
import { money } from "@/lib/format";
import { Purchase } from "./purchase";
import type { Order, Product } from "@/types";

export function Storefront({ robotId }: { robotId: string }) {
  const { state, connected, error } = useLiveState();
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
    setNotice("All yours. Thanks for stopping by!");
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 5_000);
    return () => clearTimeout(timer);
  }, [notice]);

  if (!state) return <Loading error={error} />;
  const robot = state.robots.find((r) => r.id === robotId);
  if (!robot) return <main className="loading-screen"><Brand /><h1>This Hawk hasn’t landed yet.</h1><p>Check the QR code on your robot and try again.</p><Link className="button button-primary" href="/shop/robot-001">Visit Hawk #1 <ArrowRight size={17} /></Link></main>;
  const location = state.locations.find((l) => l.id === robot.locationId)!;
  const inventory = state.inventory.filter((i) => i.robotId === robotId);
  const total = inventory.reduce((sum, item) => sum + item.stock, 0);
  const available = robot.status === "available" && !error;
  const status = robot.status === "available" ? "Ready when you are" : robot.status === "selling" ? "Helping another customer" : robot.status === "returning" ? "Heading back to base" : "Taking a quick pause";

  return <div className="storefront">
    <header className="shop-header"><Brand href={`/shop/${robotId}`} /><span className="shop-robot-tag"><span className={`status-dot ${available ? "" : "dot-amber"}`} /> {robot.name}</span></header>
    <main>
      <section className="shop-hero">
        <div className="shop-hero-copy"><span className="eyebrow"><span className="tiny-line" /> GOOD THINGS COME TO YOU</span><h1>A little break.<br /><span>Right where you are.</span></h1><p>Your autonomous storefront has arrived.</p><div className="hero-location"><MapPin size={15} /> {location.name}</div><a href="#products" className="hero-browse">Find your refreshment <ArrowDown size={15} /></a></div>
        <div className="shop-robot-art"><span className="robot-orbit orbit-one" /><span className="robot-orbit orbit-two" /><div className="robot-hello"><Sparkles size={13} /> Oh, hey there.</div><Image src="/robot.svg" width={520} height={330} alt="Hawk, your friendly autonomous mobile storefront" priority /><span className="robot-art-caption">SMALL ROBOT. BIG ON BREAKS.</span></div>
      </section>
      <div className="shop-status"><span><Radio size={17} /><strong>{status}</strong></span><span><span className="status-dot" /> {total} goodies on board</span></div>
      {error && <div className="connection-banner" role="status">We’re reconnecting to Hawk. Purchases will resume when the connection is back.</div>}
      <section className="shop-products" id="products">
        <div className="shop-section-heading"><div><span className="eyebrow">YOUR NEXT GOOD THING</span><h2>What’s your pick?</h2></div><span className="chilled-label"><Snowflake size={15} /> Chilled & ready</span></div>
        <div className="product-tabs" aria-label="Product categories">{(["all", "drinks", "snacks"] as const).map((tab) => <button key={tab} aria-pressed={category === tab} className={category === tab ? "active" : ""} onClick={() => setCategory(tab)}>{tab === "all" ? "All the good stuff" : tab === "drinks" ? "Drinks" : "Snacks"}{tab === "all" && <span>{state.products.length}</span>}</button>)}</div>
        <div className="product-grid">{state.products.filter((p) => category === "all" || p.category === category).map((product) => {
          const item = inventory.find((i) => i.productId === product.id)!;
          return <article className="product-card" key={product.id} data-testid={`product-${product.id}`}>
            <div className={`product-image product-bg-${product.id}`}><span className={`stock-pill ${item.stock <= 4 ? "stock-low" : ""}`}>{item.stock === 0 ? "Sold out" : item.stock <= 4 ? `Only ${item.stock} left` : `${item.stock} available`}</span><Image src={product.image} alt={`${product.name} product illustration`} width={240} height={300} priority={product.id === "coke"} />{product.id === "coke" && <span className="favorite-tag"><Sparkles size={12} /> Crowd favorite</span>}</div>
            <div className="product-details"><div className="product-title"><h3>{product.name}</h3><strong>{money(product.priceCents)}</strong></div><p>{product.description}</p><button className="button get-item" disabled={!available || item.stock === 0} onClick={() => { setRestored(undefined); setSelected(product); }}>{item.stock === 0 ? "Sold out" : "Get Item"}<ArrowRight size={18} /></button></div>
          </article>;
        })}<div className="break-card"><span className="break-icon"><Leaf size={27} /></span><h3>Less walking.<br />More doing.</h3><p>We bring the little things<br />that keep big ideas going.</p><span>Commerce that comes to you. <ArrowRight size={15} /></span></div></div>
      </section>
      <section className="how-it-works"><span className="eyebrow">A BREAK IN THREE LITTLE STEPS</span><div><p><span>01</span> Pick your favorite</p><ChevronRight size={16} /><p><span>02</span> Tap to unlock</p><ChevronRight size={16} /><p><span>03</span> Grab & get going</p></div></section>
    </main>
    <footer className="shop-footer"><Brand href={`/shop/${robotId}`} compact /><p>Good things. On the move.</p><Link href="/dashboard">Operator dashboard <ArrowRight size={14} /></Link><span className="demo-label"><span className={`status-dot ${connected ? "" : "dot-muted"}`} /> Demo experience · No real payments</span></footer>
    {notice && <div className="toast" role="status"><Check size={18} /> {notice}</div>}
    {selected && <Purchase product={selected} inventory={inventory.find((i) => i.productId === selected.id)!} getSessionId={() => sessionId.current} initialOrder={restored} onClose={() => { setSelected(null); setRestored(undefined); }} onComplete={completed} />}
    <div className="shop-mobile-footer"><ShoppingBag size={15} /> A storefront that comes to you.</div>
  </div>;
}
