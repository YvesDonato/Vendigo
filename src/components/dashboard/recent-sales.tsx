import Image from "next/image";
import { useState } from "react";
import { ArrowDown, ArrowUpRight } from "lucide-react";
import { money, time } from "@/lib/format";
import type { AppSnapshot } from "@/types";

export function RecentSales({ state }: { state: AppSnapshot }) {
  const [expanded, setExpanded] = useState(false);
  return <section className="panel sales-panel"><div className="panel-heading"><div><span className="eyebrow">LITTLE MOMENTS, LIVE</span><h2>Recent sales</h2></div><span className="live-label"><span className="status-dot" /> Live feed</span></div><div className="sales-table"><div className="sales-table-head"><span>PRODUCT</span><span>LOCATION</span><span>TIME</span><span>AMOUNT</span></div>{state.transactions.slice(0, expanded ? 15 : 5).map((transaction) => {
    const product = state.products.find((p) => p.id === transaction.productId)!;
    const location = state.locations.find((l) => l.id === transaction.locationId)!;
    return <div className="sale-row" key={transaction.id} data-testid={`sale-${transaction.id}`}><div className="sale-product"><span className={`sale-image product-bg-${product.id}`}><Image src={product.image} width={26} height={34} alt="" /></span><span><strong>{product.name}</strong><small>Sold · {state.robots.find((r) => r.id === transaction.robotId)?.name}</small></span></div><span className="sale-location">{location.name}</span><time dateTime={transaction.createdAt}>{time(transaction.createdAt)}</time><strong className="sale-amount">{money(transaction.amountCents)} <ArrowUpRight size={12} /></strong></div>;
  })}</div><button className="sales-more" onClick={() => setExpanded(!expanded)}>{expanded ? "Show fewer sales" : "See more good things"}<ArrowDown size={13} style={{ transform: expanded ? "rotate(180deg)" : undefined }} /></button></section>;
}
