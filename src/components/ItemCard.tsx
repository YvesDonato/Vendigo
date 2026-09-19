import Image from "next/image";
import { Check } from "lucide-react";
import { QuantityControl } from "@/components/QuantityControl";
import type { Item } from "@/lib/types";

type ItemCardProps = {
  item: Item;
  quantity: number;
  onChange: (quantity: number) => void;
  eager?: boolean;
};

export function ItemCard({ item, quantity, onChange, eager = false }: ItemCardProps) {
  const isSelected = quantity > 0;

  return (
    <article
      className={`item-card${isSelected ? " item-card-selected" : ""}${
        !item.available ? " item-card-unavailable" : ""
      }`}
    >
      <button
        className="item-select-button"
        type="button"
        onClick={() => item.available && onChange(isSelected ? 0 : 1)}
        aria-pressed={isSelected}
        aria-label={`${isSelected ? "Remove" : "Select"} ${item.name}`}
        disabled={!item.available}
      >
        <div className="item-image-pane">
          <Image
            src={item.image}
            alt=""
            fill
            loading={eager ? "eager" : "lazy"}
            sizes="(max-width: 600px) 45vw, 220px"
          />
          {isSelected && (
            <span className="selection-check" aria-hidden="true">
              <Check size={14} strokeWidth={2.4} />
            </span>
          )}
        </div>
        <span className="item-copy">
          <span className="item-name-row">
            <strong>{item.name}</strong>
            {!item.available && <span className="availability is-out">Unavailable</span>}
          </span>
        </span>
      </button>
      {item.available && isSelected && (item.quantityAvailable ?? 1) > 1 && (
        <QuantityControl
          value={quantity}
          max={item.quantityAvailable}
          onChange={onChange}
          compact
        />
      )}
    </article>
  );
}
