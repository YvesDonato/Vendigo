import { ArrowUpRight, CircleDollarSign, MousePointer2, PackageCheck, ScanLine } from "lucide-react";
import { money, time } from "@/lib/format";
import type { AppSnapshot } from "@/types";

export function Kpis({ state }: { state: AppSnapshot }) {
  const revenue = state.transactions.reduce((sum, t) => sum + t.amountCents, 0);
  const conversion = state.qrScans ? state.purchasingSessions / state.qrScans * 100 : 0;
  const values = [
    { label: "Revenue", value: money(revenue), note: "A little refreshment adds up", icon: CircleDollarSign, id: "revenue" },
    { label: "Units sold", value: state.transactions.length, note: "Good things delivered", icon: PackageCheck, id: "units" },
    { label: "QR scans", value: state.qrScans, note: "A moment of curiosity", icon: ScanLine, id: "scans" },
    { label: "Scan → purchase", value: `${conversion.toFixed(1)}%`, note: "Scanned sessions that purchased", icon: MousePointer2, id: "conversion" },
  ];
  return <div className="kpi-grid">{values.map(({ label, value, note, icon: Icon, id }) => <section className="kpi-card" key={id}><div className="kpi-label"><span>{label}</span><Icon size={17} /></div><strong data-testid={`kpi-${id}`}>{value}</strong><div className="kpi-note"><span>{note}</span><span className="kpi-accent"><ArrowUpRight size={15} /></span></div></section>)}</div>;
}

export function RevenueChart({ state }: { state: AppSnapshot }) {
  const total = state.transactions.reduce((sum, t) => sum + t.amountCents, 0);
  const top = Math.max(200, Math.ceil(total / 100 / 50) * 50);
  const start = new Date(state.startedAt).getTime() - 5 * 60 * 60 * 1000;
  const end = state.transactions.reduce((latest, t) => Math.max(latest, new Date(t.createdAt).getTime()), new Date(state.startedAt).getTime());
  const points = Array.from({ length: 7 }, (_, i) => {
    const cutoff = start + (end - start) * i / 6;
    const amount = state.transactions.filter((t) => new Date(t.createdAt).getTime() <= cutoff).reduce((sum, t) => sum + t.amountCents, 0);
    return { x: 40 + i * 87, y: 153 - amount / (top * 100) * 132, amount, at: cutoff };
  });
  const line = points.map((p) => `${p.x},${p.y}`).join(" ");
  return <section className="panel revenue-panel"><div className="panel-heading"><div><span className="eyebrow">SMALL STOPS. STEADY GROWTH.</span><h2>Good business, on the move.</h2></div><span className="small-pill"><span className="status-dot" /> This event</span></div><div className="chart-summary"><strong>{money(total)}</strong><span>cumulative revenue <ArrowUpRight size={14} /></span></div>
    <div className="revenue-chart"><svg viewBox="0 0 600 194" role="img" aria-label={`Cumulative event revenue rising to ${money(total)}`}><defs><linearGradient id="revenue-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#739c67" stopOpacity=".17" /><stop offset="100%" stopColor="#739c67" stopOpacity="0" /></linearGradient></defs>{[0, 1, 2, 3].map((i) => <g key={i}><line x1="40" y1={21 + i * 44} x2="565" y2={21 + i * 44} stroke="#e9ece3" strokeDasharray="3 4" /><text x="1" y={25 + i * 44} className="chart-label">${Math.round(top * (3 - i) / 3)}</text></g>)}<polygon points={`40,153 ${line} 562,153`} fill="url(#revenue-fill)" /><polyline points={line} fill="none" stroke="#527a48" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /><circle cx={points[6].x} cy={points[6].y} r="5" fill="#527a48" stroke="white" strokeWidth="3" />{points.filter((_, i) => i % 2 === 0).map((p) => <text key={p.x} x={p.x} y="183" textAnchor="middle" className="chart-label">{time(new Date(p.at).toISOString())}</text>)}</svg></div>
    <div className="chart-footnote"><span className="chart-legend" /> Revenue from completed pickups<span>CAD · Simulated payments</span></div>
  </section>;
}
