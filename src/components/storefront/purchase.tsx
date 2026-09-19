"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check, CircleCheck, CreditCard, LoaderCircle, LockKeyhole, ShieldCheck, TriangleAlert, UnlockKeyhole } from "lucide-react";
import { Modal } from "@/components/modal";
import { api, newId, saveSession } from "@/lib/client";
import { money } from "@/lib/format";
import type { InventoryItem, Order, Product } from "@/types";

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function Purchase({ product, inventory, getSessionId, initialOrder, onClose, onComplete }: { product: Product; inventory: InventoryItem; getSessionId: () => string; initialOrder?: Order; onClose: () => void; onComplete: () => void }) {
  const [phase, setPhase] = useState<"confirm" | "processing" | "approved" | "tracking" | "error">(initialOrder ? "tracking" : "confirm");
  const [order, setOrder] = useState<Order | null>(initialOrder ?? null);
  const [error, setError] = useState("");
  const [seconds, setSeconds] = useState(10);
  const orderId = useRef(initialOrder?.id ?? newId());
  const submitting = useRef(false);
  const storageKey = `hawk-order-${inventory.robotId}`;

  useEffect(() => {
    if (phase !== "tracking") return;
    let active = true;
    const check = () => api<Order>(`/api/orders/${orderId.current}`).then((result) => {
      if (active) { setOrder(result); setError(""); }
    }).catch(() => { if (active) setError("Reconnecting… Hawk will relock automatically."); });
    void check();
    const poll = setInterval(check, 650);
    return () => { active = false; clearInterval(poll); };
  }, [phase]);

  useEffect(() => {
    if (!order?.closesAt) return;
    const update = () => setSeconds(Math.max(0, Math.ceil((order.closesAt! - Date.now()) / 1000)));
    const timer = setInterval(update, 100);
    return () => clearInterval(timer);
  }, [order?.closesAt]);

  useEffect(() => {
    if (order?.status !== "completed") return;
    saveSession(storageKey, null);
    const timer = setTimeout(onComplete, 1_500);
    return () => clearTimeout(timer);
  }, [order?.status, onComplete, storageKey]);

  async function confirm() {
    if (submitting.current) return;
    submitting.current = true;
    setError("");
    setPhase("processing");
    await wait(750);
    setPhase("approved");
    await wait(550);
    saveSession(storageKey, JSON.stringify({ orderId: orderId.current, productId: product.id }));
    try {
      const result = await api<Order>("/api/robot/unlock", { robotId: inventory.robotId, productId: product.id, compartmentId: inventory.compartmentId, orderId: orderId.current, sessionId: getSessionId() });
      setOrder(result);
      setPhase("tracking");
    } catch (reason) {
      // A lost HTTP response may still have opened the door. Reconcile by id first.
      const existing = await api<Order>(`/api/orders/${orderId.current}`).catch(() => null);
      if (existing && existing.status !== "failed") {
        setOrder(existing);
        setPhase("tracking");
      } else {
        if (existing?.status === "failed") orderId.current = newId();
        setError(reason instanceof Error ? reason.message : "Please try again.");
        setPhase("error");
      }
    } finally { submitting.current = false; }
  }

  const complete = order?.status === "completed";
  const lockFailed = order?.status === "lock_failed";
  const failed = order?.status === "failed";
  const unlocked = order?.status === "unlocked";

  return <Modal title="Get your item" onClose={onClose} dismissible={phase === "confirm" || phase === "error" || failed} className="purchase-modal">
    <div className="purchase-steps" aria-label="Purchase progress"><span className="is-current">1 <span>Confirm</span></span><i /><span className={phase !== "confirm" ? "is-current" : ""}>2 <span>Approve</span></span><i /><span className={phase === "tracking" ? "is-current" : ""}>3 <span>Enjoy</span></span></div>
    {phase === "confirm" && <>
      <div className={`confirmation-image product-bg-${product.id}`}><Image src={product.image} alt={product.name} width={150} height={185} /></div>
      <span className="eyebrow">A little pick-me-up</span><h2>{product.name}</h2><p className="muted">One for you. Ready right here.</p>
      <div className="order-total"><span>1 × {product.name}</span><strong>{money(product.priceCents)}</strong></div>
      <button className="button button-primary button-full" onClick={confirm}>Confirm <span>{money(product.priceCents)} <ArrowRight size={18} /></span></button>
      <p className="purchase-note"><ShieldCheck size={14} /> Demo payment · You won’t be charged</p>
    </>}
    {phase === "processing" && <div className="purchase-state" role="status"><span className="state-icon"><CreditCard size={34} /></span><h2>A moment of refreshment.</h2><p>Processing your demo payment…</p><LoaderCircle className="spin" size={25} /><small>No real payment is being collected.</small></div>}
    {phase === "approved" && <div className="purchase-state" role="status"><span className="state-icon state-success"><Check size={38} /></span><h2>Payment Approved</h2><p>Getting your compartment ready.</p><span className="small-pill">{money(product.priceCents)} · Demo payment</span></div>}
    {phase === "tracking" && <div className="purchase-state" role="status">
      <span className={`state-icon ${lockFailed || failed ? "state-warning" : "state-success"}`}>{lockFailed || failed ? <TriangleAlert size={36} /> : complete ? <CircleCheck size={38} /> : unlocked ? <UnlockKeyhole size={36} /> : <LockKeyhole size={36} />}</span>
      <span className="eyebrow">Compartment {inventory.compartmentId.toString().padStart(2, "0")}</span>
      <h2>{lockFailed ? "A little help needed" : failed ? "Couldn’t unlock" : complete ? "You’re all set." : unlocked ? "Compartment unlocked" : order?.status === "locking" ? "Closing securely…" : "Opening your compartment…"}</h2>
      <p>{lockFailed || failed ? order?.error : complete ? "Locked again. Enjoy your little break!" : `Take your ${product.name}`}</p>
      {unlocked && <><div className="countdown"><svg viewBox="0 0 100 100" aria-hidden="true"><circle className="countdown-track" cx="50" cy="50" r="43" /><circle className="countdown-progress" cx="50" cy="50" r="43" pathLength="100" strokeDasharray={`${seconds * 10} 100`} /></svg><strong>{seconds}<small>seconds</small></strong></div><span className="countdown-label">Closing in {seconds} seconds</span><small>Take your item, then keep hands clear.</small></>}
      {complete && <span className="small-pill"><Check size={14} /> Purchase complete</span>}
      {failed && <button className="button button-primary" onClick={onClose}>Back to storefront</button>}
      {error && <p className="inline-error">{error}</p>}
    </div>}
    {phase === "error" && <div className="purchase-state" role="alert"><span className="state-icon state-warning"><TriangleAlert size={32} /></span><h2>Let’s try that again.</h2><p>{error}</p><button className="button button-primary button-full" onClick={confirm}>Try again <ArrowRight size={18} /></button><small>No real payment was taken.</small></div>}
  </Modal>;
}
