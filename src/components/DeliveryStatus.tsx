import { BatteryMedium, Bot, MapPinned } from "lucide-react";
import { StatusTimeline } from "@/components/StatusTimeline";
import { telemetryForStatus } from "@/lib/mockDelivery";
import type { DeliveryRequest } from "@/lib/types";

const labels = {
  queued: { eyebrow: "Request received", title: "You’re in the queue" },
  accepted: { eyebrow: "Request accepted", title: "We’re getting ready" },
  preparing: { eyebrow: "Preparing request", title: "Loading your items" },
  dispatched: { eyebrow: "On the move", title: "Vehicle dispatched" },
  arriving: { eyebrow: "Almost there", title: "Arriving now" },
  delivered: { eyebrow: "Delivery complete", title: "Your items have arrived" },
} as const;

export function DeliveryStatus({ request }: { request: DeliveryRequest }) {
  const copy = labels[request.status];
  const telemetry = telemetryForStatus(request.status);
  const statusLabel = telemetry.status.charAt(0).toUpperCase() + telemetry.status.slice(1);

  return (
    <>
      <section className="delivery-hero">
        <div className={`status-orb status-${request.status}`} aria-hidden="true">
          <span className="status-orb-core">
            {request.status === "delivered" ? "✓" : request.etaMinutes ?? "—"}
          </span>
        </div>
        <h1>{copy.title}</h1>
        {request.status !== "delivered" ? (
          <p className="arrival-copy">
            Estimated arrival <strong>{request.etaMinutes} min</strong>
          </p>
        ) : (
          <p className="arrival-copy">Ready to collect</p>
        )}
        {request.queuePosition && request.status === "queued" && (
          <span className="queue-chip">Position {request.queuePosition} in queue</span>
        )}
      </section>

      <section className="tracking-surface">
        <StatusTimeline status={request.status} />
      </section>

      <section className="map-placeholder" aria-label="Vehicle position preview">
        <div className="map-grid" aria-hidden="true" />
        <div className="map-route" aria-hidden="true">
          <span className="route-start" />
          <span className="route-destination"><MapPinned size={18} /></span>
        </div>
        <div className="map-message">
          <strong>{telemetry.location ?? "Position after dispatch"}</strong>
        </div>
      </section>

      <section className="vehicle-panel" aria-labelledby="vehicle-heading">
        <div className="vehicle-identity">
          <span className="vehicle-icon" aria-hidden="true"><Bot size={22} /></span>
          <span>
            <strong id="vehicle-heading">{telemetry.robotId}</strong>
            <small>{statusLabel}</small>
          </span>
        </div>
        <div className="battery-status" aria-label={`Battery ${telemetry.battery} percent`}>
          <BatteryMedium size={19} aria-hidden="true" />
          <span>{telemetry.battery}%</span>
        </div>
      </section>
    </>
  );
}
