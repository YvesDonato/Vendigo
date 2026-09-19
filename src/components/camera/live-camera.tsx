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
    <div className="panel-heading"><div><span className="eyebrow">A view from the ground</span><h2>Live Robot Camera</h2></div><Camera size={19} className="muted" /></div>
    <div className={`camera-view ${status === "online" ? "is-online" : ""}`}>
      {configured && status !== "offline" && <img key={attempt} src={`/api/camera/stream?attempt=${attempt}`} alt="Live view from Hawk #1’s onboard camera" onLoad={() => setStatus("online")} onError={() => setStatus("offline")} />}
      {status !== "online" && <div className="camera-fallback"><span className="camera-off-icon">{status === "connecting" ? <Radio size={27} /> : <VideoOff size={27} />}</span><strong>{status === "connecting" ? "Connecting to Hawk…" : "Waiting for a little perspective"}</strong><p>{status === "connecting" ? "Establishing the camera feed." : "The onboard camera is offline. Your store is still open."}</p><button className="camera-retry" onClick={() => { setConfigured(false); setStatus("connecting"); setAttempt((n) => n + 1); }}><RotateCw size={13} /> Reconnect camera</button></div>}
      <div className="camera-overlay"><span><span className={`status-dot ${status === "online" ? "" : "dot-muted"}`} /> {status === "online" ? "LIVE" : "STANDBY"}</span><span>HAWK #1 · CAM 01</span></div>
    </div>
    <div className="camera-footer"><span>Onboard ESP32 camera</span><span className={status === "online" ? "text-green" : "muted"}>{status === "online" ? "Feed connected" : "No signal"}</span></div>
  </section>;
}
