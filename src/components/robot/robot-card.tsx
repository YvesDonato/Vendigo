"use client";

import { useState } from "react";
import { BatteryMedium, Camera, Home, LoaderCircle, LockKeyhole, Package, Pause, Play, UnlockKeyhole } from "lucide-react";
import { api } from "@/lib/client";
import type { AppSnapshot, Robot, RobotCommand } from "@/types";
import type { CameraStatus } from "@/components/camera/live-camera";

const statusLabels = { available: "", selling: "Pickup in progress", stopped: "Stopped", returning: "Returning to base" };

export function RobotCard({ robot, state, cameraStatus }: { robot: Robot; state: AppSnapshot; cameraStatus: CameraStatus }) {
  const [pending, setPending] = useState<RobotCommand | null>(null);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [compartment, setCompartment] = useState(1);
  const inventory = state.inventory.filter((i) => i.robotId === robot.id);
  const count = inventory.reduce((sum, i) => sum + i.stock, 0);
  const capacity = inventory.reduce((sum, i) => sum + i.capacity, 0);
  const percent = Math.round(count / capacity * 100);
  const active = state.activeOrders.find((order) => order.robotId === robot.id);

  async function command(value: RobotCommand) {
    if (pending) return;
    setPending(value); setMessage(""); setFailed(false);
    try {
      await api("/api/robot/command", { robotId: robot.id, command: value, compartmentId: compartment });
      setMessage(value === "stop" ? "Vendigo stopped." : value === "resume" ? "Purchases resumed." : value === "return-to-base" ? "Return to base started." : value === "retry-lock" ? "Lock retry sent." : `Compartment ${compartment} opened. Locks in 7 seconds.`);
    } catch (error) { setFailed(true); setMessage(error instanceof Error ? error.message : "Command failed. Please try again."); }
    finally { setPending(null); }
  }

  return <section className="panel robot-panel" id="robot">
    <div className="panel-heading"><h2>Robot controls</h2>{robot.status !== "available" && <span className="panel-detail">{statusLabels[robot.status]}</span>}</div>
    <div className="robot-vitals"><div><BatteryMedium size={17} /><span>Battery</span><strong>{robot.battery}%</strong></div><div><Package size={16} /><span>Inventory</span><strong>{percent}%</strong></div><div><Camera size={16} /><span>Camera</span><strong className={cameraStatus === "online" ? "text-blue" : "muted"}>{cameraStatus === "online" ? "Online" : cameraStatus === "connecting" ? "Connecting" : "Offline"}</strong></div></div>
    <div className={`compartment-state ${active ? "door-open" : ""}`} data-testid="compartment-state">{active ? <UnlockKeyhole size={15} /> : <LockKeyhole size={15} />}<span>{active ? `Compartment ${active.compartmentId} · ${active.status === "lock_failed" ? "needs lock retry" : active.status === "locking" ? "relocking" : active.status === "opening" ? "opening" : "unlocked"}` : "All compartments locked"}</span></div>
    <div className="robot-controls"><button className="button button-stop" disabled={!!pending || robot.status === "stopped"} onClick={() => command("stop")}><Pause size={14} /> Stop</button><button className="button button-secondary" disabled={!!pending || !!active || robot.status === "available"} onClick={() => command("resume")}><Play size={14} /> Resume</button><button className="button button-secondary" disabled={!!pending || !!active || robot.status === "returning"} onClick={() => command("return-to-base")}><Home size={14} /> Return to Base</button></div>
    <div className="unlock-controls"><select aria-label="Compartment to unlock" value={compartment} onChange={(e) => setCompartment(Number(e.target.value))} disabled={!!active || !!pending}>{inventory.map((i) => <option key={i.compartmentId} value={i.compartmentId}>{i.compartmentId.toString().padStart(2, "0")} · {state.products.find((p) => p.id === i.productId)!.name}</option>)}</select><button className="button button-secondary" disabled={!!pending || (!!active && active.status !== "lock_failed") || robot.status === "returning"} onClick={() => command(active?.status === "lock_failed" ? "retry-lock" : "unlock")}>{pending ? <LoaderCircle className="spin" size={14} /> : <UnlockKeyhole size={14} />}{active?.status === "lock_failed" ? "Retry lock" : "Unlock Compartment"}</button></div>
    {message && <p className={`command-message ${failed ? "inline-error" : ""}`} role="status">{message}</p>}
  </section>;
}
