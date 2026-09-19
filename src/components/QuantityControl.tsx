import { Minus, Plus } from "lucide-react";

type QuantityControlProps = {
  value: number;
  max?: number;
  onChange: (value: number) => void;
  compact?: boolean;
};

export function QuantityControl({
  value,
  max = 99,
  onChange,
  compact = false,
}: QuantityControlProps) {
  return (
    <div
      className={`quantity-control${compact ? " quantity-control-compact" : ""}`}
      aria-label="Quantity"
    >
      <button
        type="button"
        className="quantity-button"
        onClick={() => onChange(Math.max(0, value - 1))}
        aria-label="Decrease quantity"
      >
        <Minus size={15} strokeWidth={2} aria-hidden="true" />
      </button>
      <output aria-live="polite" aria-label={`Quantity ${value}`}>
        {value}
      </output>
      <button
        type="button"
        className="quantity-button"
        onClick={() => onChange(Math.min(max, value + 1))}
        aria-label="Increase quantity"
        disabled={value >= max}
      >
        <Plus size={15} strokeWidth={2} aria-hidden="true" />
      </button>
    </div>
  );
}
