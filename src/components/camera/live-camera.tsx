"use client";

/* Native MJPEG must use an unoptimized img: Next Image cannot proxy an infinite stream. */
/* eslint-disable @next/next/no-img-element */
import { useEffect, useState } from "react";
import { Camera, Radio, RotateCw, VideoOff } from "lucide-react";

export type CameraStatus = "connecting" | "online" | "offline";

export function LiveCamera({ onStatus }: { onStatus: (status: CameraStatus) => void }) {
  const [status, setStatus] = useState<CameraStatus>("connecting");
  const [configured, setConfigured] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => { onStatus(status); }, [status, onStatus]);
  useEffect(() => {
    let active = true;
    fetch("/api/camera/status").then((r) => r.json()).then((data) => {
      if (!active) return;
      setConfigured(data.configured);
      setStatus(data.configured ? "connecting" : "offline");
    }).catch(() => { if (active) setStatus("offline"); });
    return () => { active = false; };
  }, [attempt]);

  useEffect(() => {
    if (status !== "connecting") return;
    const timeout = setTimeout(() => setStatus("offline"), 8_000);
    return () => clearTimeout(timeout);
  }, [status, attempt]);

  return <section className="panel camera-panel" id="camera">
    <div className="panel-heading"><h2>Live Robot Camera</h2><Camera size={19} className="muted" /></div>
    <div className={`camera-view ${status === "online" ? "is-online" : ""}`}>
      {configured && status !== "offline" && <img key={attempt} src={`/api/camera/stream?attempt=${attempt}`} alt="Live onboard camera feed" onLoad={() => setStatus("online")} onError={() => setStatus("offline")} />}
      {status !== "online" && <div className="camera-fallback"><span className="camera-off-icon">{status === "connecting" ? <Radio size={27} /> : <VideoOff size={27} />}</span><strong>{status === "connecting" ? "Connecting…" : "Camera offline"}</strong><button className="button button-secondary" onClick={() => { setConfigured(false); setStatus("connecting"); setAttempt((n) => n + 1); }}><RotateCw size={15} /> Reconnect camera</button></div>}
    </div>
    {status === "online" && <p className="camera-caption">Feed connected</p>}
  </section>;
}
