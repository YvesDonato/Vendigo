import { Check } from "lucide-react";
import type { DeliveryStatus as DeliveryStatusType } from "@/lib/types";

const timeline = [
  { label: "Request received", statuses: ["queued", "accepted"] },
  { label: "Preparing", statuses: ["preparing"] },
  { label: "Vehicle dispatched", statuses: ["dispatched"] },
  { label: "Arriving", statuses: ["arriving"] },
  { label: "Delivered", statuses: ["delivered"] },
] as const;

const rank: Record<DeliveryStatusType, number> = {
  queued: 0,
  accepted: 0,
  preparing: 1,
  dispatched: 2,
  arriving: 3,
  delivered: 4,
};

export function StatusTimeline({ status }: { status: DeliveryStatusType }) {
  const current = rank[status];

  return (
    <ol className="status-timeline" aria-label="Delivery progress">
      {timeline.map((step, index) => {
        const complete = index < current || status === "delivered";
        const active = index === current && status !== "delivered";
        return (
          <li
            className={`${complete ? "is-complete" : ""}${active ? " is-active" : ""}`}
            key={step.label}
          >
            <span className="timeline-marker" aria-hidden="true">
              {complete ? <Check size={12} strokeWidth={2.6} /> : <span />}
            </span>
            <span>{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}
