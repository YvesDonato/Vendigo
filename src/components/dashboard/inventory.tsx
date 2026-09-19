import Image from "next/image";
import { TriangleAlert } from "lucide-react";
import type { AppSnapshot } from "@/types";

export function InventoryPanel({ state }: { state: AppSnapshot }) {
  const stock = state.inventory.reduce((sum, i) => sum + i.stock, 0);
  const capacity = state.inventory.reduce((sum, i) => sum + i.capacity, 0);
  const low = state.inventory.filter((i) => i.stock <= 4);
  return <section className="panel inventory-panel" id="inventory"><div className="panel-heading"><h2>Inventory</h2><span className="panel-detail"><span data-testid="inventory-total">{stock}</span> / {capacity}</span></div><div className="inventory-list">{state.inventory.map((item) => {
    const product = state.products.find((p) => p.id === item.productId)!;
    return <div className="inventory-row" key={`${item.robotId}-${item.productId}`} data-testid={`inventory-${item.productId}`}><div className="inventory-image"><Image src={product.image} width={32} height={44} alt="" /></div><div className="inventory-info"><div><strong>{product.name}</strong><span className={item.stock <= 4 ? "text-amber" : ""}>{item.stock}<span className="muted"> / {item.capacity}</span></span></div><div className="inventory-track" role="progressbar" aria-label={`${product.name} stock`} aria-valuenow={item.stock} aria-valuemin={0} aria-valuemax={item.capacity}><span className={item.stock <= 4 ? "stock-low" : ""} style={{ width: `${item.stock / item.capacity * 100}%` }} /></div></div></div>;
  })}</div>{low.length > 0 && <div className="inventory-warning"><TriangleAlert size={15} /><span>Low stock: {low.map((i) => state.products.find((p) => p.id === i.productId)!.name).join(", ")}.</span></div>}</section>;
}
