import type { ReactNode } from "react";

type BottomActionBarProps = {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
  meta?: ReactNode;
};

export function BottomActionBar({
  label,
  onClick,
  disabled,
  loading,
  meta,
}: BottomActionBarProps) {
  return (
    <div className="bottom-action-shell">
      <div className="bottom-action-bar">
        {meta && <div className="action-meta">{meta}</div>}
        <button
          className="button button-primary button-wide"
          type="button"
          onClick={onClick}
          disabled={disabled || loading}
        >
          {loading ? <span className="button-loader" aria-label="Loading" /> : label}
        </button>
      </div>
    </div>
  );
}
