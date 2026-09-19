"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

export function Modal({ children, title, onClose, dismissible = true, className = "" }: { children: ReactNode; title: string; onClose: () => void; dismissible?: boolean; className?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      dialog.close();
      document.body.style.overflow = overflow;
      if (trigger?.isConnected) trigger.focus({ preventScroll: true });
    };
  }, []);
  return <dialog ref={ref} aria-label={title} className={`modal ${className}`} onCancel={(event) => { event.preventDefault(); if (dismissible) onClose(); }}>
    {dismissible && <button className="icon-button modal-close" onClick={onClose} aria-label="Close dialog"><X size={20} /></button>}
    {children}
  </dialog>;
}
