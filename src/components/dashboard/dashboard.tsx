"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowUpRight, Camera, ChevronRight, CircleHelp, Command, LayoutGrid, Leaf, Map, Package, Radio, ScanLine, Store, Zap } from "lucide-react";
import { Brand } from "@/components/brand";
import { Loading } from "@/components/loading";
import { LiveCamera, type CameraStatus } from "@/components/camera/live-camera";
import { RobotCard } from "@/components/robot/robot-card";
import { useLiveState } from "@/hooks/use-live-state";
import { Kpis, RevenueChart } from "./analytics";
import { InventoryPanel } from "./inventory";
import { VenuePanel } from "./venue";
import { RecentSales } from "./recent-sales";
import { RobotQr } from "./qr-code";

export function Dashboard() {
  const { state, connected, error } = useLiveState();
  const [cameraStatus, setCameraStatus] = useState<CameraStatus>("connecting");
  const [showQr, setShowQr] = useState(false);
  const [active, setActive] = useState("overview");
  if (!state) return <Loading error={error} />;
  const robot = state.robots[0];

  return <div className="dashboard-shell">
    <aside className="sidebar"><Brand href="/dashboard" /><div className="workspace-label"><span className="workspace-icon"><Command size={17} /></span><div><strong>Hack the North</strong><span>Event workspace</span></div><span className="workspace-tag">LIVE</span></div><span className="nav-label">WORKSPACE</span><nav aria-label="Dashboard sections">{[{ id: "overview", name: "Overview", icon: LayoutGrid }, { id: "inventory", name: "Inventory", icon: Package }, { id: "venue", name: "Venue intelligence", icon: Map }, { id: "robot", name: "Your robot", icon: Radio }, { id: "camera", name: "Live camera", icon: Camera }].map(({ id, name, icon: Icon }) => <a key={id} className={active === id ? "active" : ""} href={`#${id}`} onClick={() => setActive(id)}><Icon size={17} />{name}{id === "overview" && <span className="nav-active-dot" />}</a>)}</nav><div className="sidebar-bottom"><div className="sidebar-note"><span><Leaf size={17} /> Small footprint.<br />&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Big possibilities.</span><p>Commerce that comes to you.</p></div><Link className="sidebar-store-link" href={`/shop/${robot.id}`} target="_blank"><Store size={17} /> Open storefront <ArrowUpRight size={14} /></Link><div className="operator-profile"><span>HT</span><div><strong>Event operator</strong><small>Hawk-2-U demo</small></div><CircleHelp size={16} /></div></div></aside>
    <div className="dashboard-body"><header className="dashboard-header"><div className="breadcrumbs"><span>Workspace</span><ChevronRight size={13} /><strong>Overview</strong></div><div className="header-right"><span className={`connection-label ${connected ? "" : "text-amber"}`}><span className={`status-dot ${connected ? "" : "dot-amber"}`} />{connected ? "Live updates connected" : error ? "Reconnecting" : "Syncing updates"}</span><span className="header-divider" /><span className="event-date">{new Date(state.startedAt).toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" })}</span><span className="header-avatar">HT</span></div></header>
      <main className="dashboard-main" id="overview"><div className="overview-heading"><div><div className="eyebrow"><span className="tiny-line" /> OPERATIONS, WITH A LITTLE MOMENTUM</div><h1>Good things are moving<span>.</span></h1><p>Your storefront is out there. Here’s the bigger picture.</p></div><div className="overview-actions"><Link className="button button-secondary" href={`/shop/${robot.id}`} target="_blank">View storefront <ArrowUpRight size={15} /></Link><button className="button button-primary" onClick={() => setShowQr(true)}><ScanLine size={16} /> Robot QR</button></div></div>
        {error && <div className="connection-banner" role="status">Connection interrupted. Showing the latest available data; reconnecting automatically.</div>}
        <Kpis state={state} />
        <div className="dashboard-columns"><div className="dashboard-primary"><RevenueChart state={state} /><VenuePanel state={state} /><RecentSales state={state} /></div><div className="dashboard-secondary"><RobotCard robot={robot} state={state} cameraStatus={cameraStatus} /><InventoryPanel state={state} /><LiveCamera onStatus={setCameraStatus} /></div></div>
        <footer className="dashboard-footer"><span><span className="status-dot" /> {state.robots.length} robot in your fleet <span>·</span> A world of possibilities.</span><span><Zap size={12} /> Powered by a little initiative. Hawk-2-U.</span></footer>
      </main>
    </div>{showQr && <RobotQr robotId={robot.id} onClose={() => setShowQr(false)} />}
  </div>;
}
