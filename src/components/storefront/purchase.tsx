"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, CircleCheck, LoaderCircle, LockKeyhole, TriangleAlert, UnlockKeyhole } from "lucide-react";
import { Modal } from "@/components/modal";
import { api, newId, saveSession } from "@/lib/client";
import { priceLabel } from "@/lib/format";
import type { InventoryItem, Order, Product } from "@/types";

export function Purchase({ product, inventory, getSessionId, initialOrder, onClose, onComplete }: { product: Product; inventory: InventoryItem; getSessionId: () => string; initialOrder?: Order; onClose: () => void; onComplete: () => void }) {
  const [phase, setPhase] = useState<"confirm" | "opening" | "tracking" | "error">(initialOrder ? "tracking" : "confirm");
  const [order, setOrder] = useState<Order | null>(initialOrder ?? null);
  const [error, setError] = useState("");
  const [seconds, setSeconds] = useState(7);
  const orderId = useRef(initialOrder?.id ?? newId());
  const submitting = useRef(false);
  const storageKey = `hawk-order-${inventory.robotId}`;

  useEffect(() => {
    if (phase !== "tracking") return;
    let active = true;
    const check = () => api<Order>(`/api/orders/${orderId.current}`).then((result) => {
      if (active) { setOrder(result); setError(""); }
    }).catch(() => { if (active) setError("Reconnecting… Vendigo will relock automatically."); });
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
    setPhase("opening");
    saveSession(storageKey, JSON.stringify({ orderId: orderId.current, productId: product.id }));
    try {
      const result = await api<Order>("/api/purchases", { robotId: inventory.robotId, productId: product.id, compartmentId: inventory.compartmentId, orderId: orderId.current, sessionId: getSessionId() });
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
    {phase === "confirm" && <>
      <div className="confirmation-image"><Image src={product.image} alt={product.name} width={150} height={185} /></div>
      <h2>{product.name}</h2>
      <div className="order-total"><span>1 × {product.name}</span><strong>{priceLabel(product.priceCents)}</strong></div>
      <button className="button button-primary button-full" onClick={confirm} disabled={inventory.stock < 1}>Confirm <ArrowRight size={18} /></button>
    </>}
    {phase === "opening" && <div className="purchase-state" role="status"><span className="state-icon"><UnlockKeyhole size={34} /></span><h2>Opening your compartment…</h2><LoaderCircle className="spin" size={25} /></div>}
    {phase === "tracking" && <div className="purchase-state" role="status">
      <span className={`state-icon ${lockFailed || failed ? "state-warning" : "state-success"}`}>{lockFailed || failed ? <TriangleAlert size={36} /> : complete ? <CircleCheck size={38} /> : unlocked ? <UnlockKeyhole size={36} /> : <LockKeyhole size={36} />}</span>
      <span className="eyebrow">Compartment {inventory.compartmentId.toString().padStart(2, "0")}</span>
      <h2>{lockFailed ? "Please ask the operator" : failed ? "Couldn’t unlock" : complete ? "Pickup complete" : unlocked ? "Compartment unlocked" : order?.status === "locking" ? "Closing securely…" : "Opening your compartment…"}</h2>
      <p>{lockFailed || failed ? order?.error : complete ? "Compartment locked. Enjoy!" : `Take your ${product.name}`}</p>
      {unlocked && <><div className="countdown"><svg viewBox="0 0 100 100" aria-hidden="true"><circle className="countdown-track" cx="50" cy="50" r="43" /><circle className="countdown-progress" cx="50" cy="50" r="43" pathLength="100" strokeDasharray={`${seconds / 7 * 100} 100`} /></svg><strong>{seconds}<small>seconds</small></strong></div><span className="countdown-label">Closing in {seconds} seconds</span><small>Take your item, then keep hands clear.</small></>}
      {failed && <button className="button button-primary" onClick={onClose}>Back to storefront</button>}
      {error && <p className="inline-error">{error}</p>}
    </div>}
    {phase === "error" && <div className="purchase-state" role="alert"><span className="state-icon state-warning"><TriangleAlert size={32} /></span><h2>Let’s try that again.</h2><p>{error}</p><button className="button button-primary button-full" onClick={confirm}>Try again <ArrowRight size={18} /></button></div>}
  </Modal>;
}
