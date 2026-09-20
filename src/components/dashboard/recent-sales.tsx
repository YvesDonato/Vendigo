import { useState } from "react";
import { priceLabel, time } from "@/lib/format";
import type { AppSnapshot } from "@/types";

export function RecentSales({ state }: { state: AppSnapshot }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <section className="panel sales-panel">
      <div className="panel-heading"><h2>Recent Purchases</h2></div>
      <div className="sales-list">
        {state.transactions.length === 0 && <p className="empty-purchases">Completed purchases will appear here.</p>}
        {[...state.transactions].sort((a, b) => b.createdAt.localeCompare(a.createdAt)).slice(0, expanded ? 20 : 10).map((transaction) => {
          const name = transaction.productName ?? state.products.find((p) => p.id === transaction.productId)?.name ?? transaction.productId;
          return (
            <div className="sale-row" key={transaction.id} data-testid={`sale-${transaction.id}`}>
              <div className="sale-product"><strong>{name}</strong><small className="order-reference">Order {transaction.id}</small></div>
              <div className="sale-details"><strong>{priceLabel(transaction.amountCents)}</strong><time dateTime={transaction.createdAt}>{time(transaction.createdAt)}</time></div>
            </div>
          );
        })}
      </div>
      {state.transactions.length > 10 && <button className="sales-more" onClick={() => setExpanded(!expanded)}>{expanded ? "Show fewer" : "Show more"}</button>}
    </section>
  );
}
