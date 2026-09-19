import { ItemCard } from "@/components/ItemCard";
import type { Item, Selection } from "@/lib/types";

type ItemGridProps = {
  items: Item[];
  selections: Selection;
  onQuantityChange: (itemId: string, quantity: number) => void;
};

export function ItemGrid({ items, selections, onQuantityChange }: ItemGridProps) {
  return (
    <div className="item-grid">
      {items.map((item, index) => (
        <ItemCard
          key={item.id}
          item={item}
          eager={index < 2}
          quantity={selections[item.id] ?? 0}
          onChange={(quantity) => onQuantityChange(item.id, quantity)}
        />
      ))}
    </div>
  );
}
