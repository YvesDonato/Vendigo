import type { AppSnapshot } from "../types/index.ts";

export function metrics(state: AppSnapshot) {
  const purchases = state.transactions.length;
  return {
    purchases,
    revenueCents: state.transactions.reduce((sum, purchase) => sum + purchase.amountCents, 0),
    qrScans: state.qrScans,
    conversion: state.qrScans === 0 ? 0 : purchases / state.qrScans * 100,
    itemsRemaining: state.inventory.reduce((sum, item) => sum + item.stock, 0),
  };
}
