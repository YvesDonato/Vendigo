"use client";

/* eslint-disable @next/next/no-img-element */
import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { ArrowUpRight, Check, Copy, Download, ScanLine } from "lucide-react";
import { Modal } from "@/components/modal";

export function RobotQr({ robotId, onClose }: { robotId: string; onClose: () => void }) {
  const [image, setImage] = useState("");
  const [url, setUrl] = useState("");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const origin = process.env.NEXT_PUBLIC_SHOP_ORIGIN || window.location.origin;
    const link = `${origin.replace(/\/$/, "")}/shop/${robotId}`;
    QRCode.toDataURL(link, { width: 600, margin: 3, color: { dark: "#204b38", light: "#ffffff" }, errorCorrectionLevel: "M" }).then((data) => { setImage(data); setUrl(link); }).catch(() => setError("Couldn’t generate the QR code. Please reopen this panel."));
  }, [robotId]);

  async function copy() {
    try { await navigator.clipboard.writeText(url); setCopied(true); }
    catch { setError("Select and copy the storefront address below."); }
  }

  return <Modal title="Hawk #1 storefront QR code" onClose={onClose} className="qr-modal">
    <span className="state-icon"><ScanLine size={28} /></span><span className="eyebrow">THE SHORTEST WAY TO A BREAK</span><h2>Scan. Pick. Enjoy.</h2><p>One little code. A whole storefront.</p>
    {image ? <img className="qr-image" src={image} alt={`QR code for ${url}`} width={240} height={240} /> : <div className="qr-loading">Preparing your QR code…</div>}
    <strong>Hawk #1</strong><a className="qr-url" href={url} target="_blank" rel="noreferrer">{url} <ArrowUpRight size={13} /></a>
    {url.includes("localhost") || url.includes("127.0.0.1") ? <p className="qr-lan-note">For phone scans, open this dashboard using your computer’s Wi-Fi IP address, or set NEXT_PUBLIC_SHOP_ORIGIN before starting the app.</p> : <p className="qr-lan-note">Place this code on Hawk. Phones must be able to reach this address.</p>}
    <div className="qr-actions"><button className="button button-secondary" onClick={copy} disabled={!url}>{copied ? <Check size={16} /> : <Copy size={16} />}{copied ? "Copied" : "Copy link"}</button><a className="button button-primary" href={image || undefined} download={`hawk-2-u-${robotId}-qr.png`}><Download size={16} /> Download QR</a></div>
    {error && <p className="inline-error" role="alert">{error}</p>}
  </Modal>;
}
