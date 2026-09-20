"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowUpRight, LayoutGrid, Package, ScanLine } from "lucide-react";
import { Brand } from "@/components/brand";
import { Loading } from "@/components/loading";
import { useLiveState } from "@/hooks/use-live-state";
import { Kpis, RevenueChart } from "./analytics";
import { InventoryPanel } from "./inventory";
import { RecentSales } from "./recent-sales";
import { RobotQr } from "./qr-code";

const sections = [
  { id: "overview", name: "Overview", icon: LayoutGrid },
  { id: "inventory", name: "Inventory", icon: Package },
];

export function Dashboard() {
  const { state, error } = useLiveState();
  const [showQr, setShowQr] = useState(false);
  const [active, setActive] = useState("overview");
  if (!state) return <Loading error={error} />;
  const robot = state.robots[0];

  return (
    <div className="dashboard-shell">
      <aside className="sidebar">
        <Brand href="/dashboard" />
        <nav aria-label="Dashboard sections">
          {sections.map(({ id, name, icon: Icon }) => (
            <a key={id} className={active === id ? "active" : ""} href={`#${id}`} onClick={() => setActive(id)} aria-current={active === id ? "location" : undefined}>
              <Icon size={20} /><span>{name}</span>
            </a>
          ))}
        </nav>
      </aside>
      <div className="dashboard-body">
        <header className="dashboard-header">
          <Brand href="/dashboard" />
        </header>
        <main className="dashboard-main" id="overview">
          <div className="overview-heading">
            <h1>Dashboard</h1>
            <div className="overview-actions">
              <Link className="button button-secondary" href="/shop" target="_blank">Storefront <ArrowUpRight size={16} /></Link>
              <button className="button button-primary" onClick={() => setShowQr(true)}><ScanLine size={18} /> Shop QR</button>
            </div>
          </div>
          {error && <div className="connection-banner" role="status">Connection interrupted. Reconnecting…</div>}
          <Kpis state={state} />
          <div className="dashboard-grid">
            <RevenueChart state={state} />
            <InventoryPanel state={state} />
            <RecentSales state={state} />
          </div>
        </main>
      </div>
      {showQr && <RobotQr robotId={robot.id} onClose={() => setShowQr(false)} />}
    </div>
  );
}
