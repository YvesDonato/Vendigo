import Image from "next/image";
import Link from "next/link";
import { MapPin } from "lucide-react";
import { QuantityControl } from "@/components/QuantityControl";
import { items } from "@/data/items";
import type { Selection } from "@/lib/types";

type RequestSummaryProps = {
  selections: Selection;
  locationLabel: string;
  editable?: boolean;
  onQuantityChange?: (itemId: string, quantity: number) => void;
};

export function RequestSummary({
  selections,
  locationLabel,
  editable = false,
  onQuantityChange,
}: RequestSummaryProps) {
  const selectedItems = Object.entries(selections)
    .map(([id, quantity]) => ({ item: items.find((item) => item.id === id), quantity }))
    .filter((entry): entry is { item: (typeof items)[number]; quantity: number } =>
      Boolean(entry.item),
    );

  return (
    <div className="request-summary">
      <section className="summary-section" aria-labelledby="items-heading">
        <div className="summary-heading-row">
          <h2 id="items-heading">Items</h2>
          {editable && <Link href="/">Edit</Link>}
        </div>
        <div className="summary-items">
          {selectedItems.map(({ item, quantity }) => (
            <div className="summary-item" key={item.id}>
              <div className="summary-thumbnail">
                <Image src={item.image} alt="" fill sizes="56px" />
              </div>
              <div className="summary-item-copy">
                <strong>{item.name}</strong>
              </div>
              {editable && onQuantityChange && (item.quantityAvailable ?? 1) > 1 ? (
                <QuantityControl
                  value={quantity}
                  max={item.quantityAvailable}
                  onChange={(next) => onQuantityChange(item.id, next)}
                  compact
                />
              ) : (
                quantity > 1 && <span className="summary-quantity">×{quantity}</span>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="summary-section" aria-labelledby="destination-heading">
        <div className="summary-heading-row">
          <h2 id="destination-heading">Destination</h2>
          {editable && <Link href="/location">Edit</Link>}
        </div>
        <div className="destination-row">
          <span className="location-icon" aria-hidden="true">
            <MapPin size={18} strokeWidth={1.8} />
          </span>
          <span>{locationLabel}</span>
        </div>
      </section>
    </div>
  );
}
