import { money, time } from "@/lib/format";
import type { AppSnapshot } from "@/types";

export function Kpis({ state }: { state: AppSnapshot }) {
  const revenue = state.transactions.reduce((sum, t) => sum + t.amountCents, 0);
  const conversion = state.qrScans ? state.purchasingSessions / state.qrScans * 100 : 0;
  const values = [
    { label: "Revenue", value: money(revenue), id: "revenue" },
    { label: "Units sold", value: state.transactions.length, id: "units" },
    { label: "QR scans", value: state.qrScans, id: "scans" },
    { label: "Scan → purchase", value: `${conversion.toFixed(1)}%`, id: "conversion" },
  ];
  return (
    <div className="kpi-grid">
      {values.map(({ label, value, id }) => (
        <section className="kpi-card" key={id}>
          <span className="kpi-label">{label}</span>
          <strong data-testid={`kpi-${id}`}>{value}</strong>
        </section>
      ))}
    </div>
  );
}

export function RevenueChart({ state }: { state: AppSnapshot }) {
  const total = state.transactions.reduce((sum, t) => sum + t.amountCents, 0);
  const top = Math.max(200, Math.ceil(total / 100 / 50) * 50);
  const start = new Date(state.startedAt).getTime() - 5 * 60 * 60 * 1000;
  const end = state.transactions.reduce((latest, t) => Math.max(latest, new Date(t.createdAt).getTime()), new Date(state.startedAt).getTime());
  const points = Array.from({ length: 7 }, (_, i) => {
    const cutoff = start + (end - start) * i / 6;
    const amount = state.transactions.filter((t) => new Date(t.createdAt).getTime() <= cutoff).reduce((sum, t) => sum + t.amountCents, 0);
    return { x: 44 + i * 86, y: 156 - amount / (top * 100) * 132, at: cutoff };
  });
  const line = points.map((p) => `${p.x},${p.y}`).join(" ");

  return (
    <section className="panel revenue-panel">
      <div className="panel-heading"><h2>Revenue over time</h2><span className="panel-detail">CAD</span></div>
      <div className="chart-summary"><strong>{money(total)}</strong></div>
      <div className="revenue-chart">
        <svg viewBox="0 0 600 204" role="img" aria-label={`Cumulative event revenue: ${money(total)}`}>
          {[0, 1, 2, 3].map((i) => (
            <g key={i}>
              <line x1="44" y1={24 + i * 44} x2="562" y2={24 + i * 44} stroke="#e6eff5" strokeDasharray="3 5" />
              <text x="0" y={28 + i * 44} className="chart-label">${Math.round(top * (3 - i) / 3)}</text>
            </g>
          ))}
          <polygon points={`44,156 ${line} 560,156`} fill="#e8f6ff" />
          <polyline points={line} fill="none" stroke="#55b7ed" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx={points[6].x} cy={points[6].y} r="4" fill="#1786c3" />
          {points.filter((_, i) => i % 2 === 0).map((p) => <text key={p.x} x={p.x} y="193" textAnchor="middle" className="chart-label">{time(new Date(p.at).toISOString())}</text>)}
        </svg>
      </div>
    </section>
  );
}
