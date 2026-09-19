import { useState } from "react";
import { priceLabel, time } from "@/lib/format";
import type { AppSnapshot } from "@/types";

export function RecentSales({ state }: { state: AppSnapshot }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <section className="panel sales-panel">
      <div className="panel-heading"><h2>Recent sales</h2></div>
      <div className="sales-list">
        {state.transactions.slice(0, expanded ? 15 : 5).map((transaction) => {
          const product = state.products.find((p) => p.id === transaction.productId)!;
          return (
            <div className="sale-row" key={transaction.id} data-testid={`sale-${transaction.id}`}>
              <div className="sale-product"><strong>{product.name}</strong></div>
              <div className="sale-details"><strong>{priceLabel(transaction.amountCents)}</strong><time dateTime={transaction.createdAt}>{time(transaction.createdAt)}</time></div>
            </div>
          );
        })}
      </div>
      <button className="sales-more" onClick={() => setExpanded(!expanded)}>{expanded ? "Show fewer" : "Show more"}</button>
    </section>
  );
}
