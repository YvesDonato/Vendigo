import { items } from "@/data/items";
import { locations } from "@/data/locations";
import type {
  DeliveryRequest,
  DeliveryStatus,
  RobotTelemetry,
  Selection,
} from "@/lib/types";

const delay = (milliseconds: number) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

export async function getAvailableItems() {
  return items.filter((item) => item.available);
}

export async function getVenueLocations() {
  return locations;
}

export async function createDeliveryRequest(input: {
  selections: Selection;
  locationId: string;
  locationLabel: string;
}): Promise<DeliveryRequest> {
  await delay(450);
  const now = new Date().toISOString();

  return {
    id: `RQ-${Math.random().toString(36).slice(2, 7).toUpperCase()}`,
    items: Object.entries(input.selections).map(([itemId, quantity]) => ({
      itemId,
      quantity,
    })),
    locationId: input.locationId,
    locationLabel: input.locationLabel,
    status: "queued",
    queuePosition: 2,
    etaMinutes: 8,
    createdAt: now,
    statusUpdatedAt: now,
  };
}

export async function getDeliveryStatus(request: DeliveryRequest) {
  return request;
}

export function subscribeToDeliveryUpdates(
  _requestId: string,
  _onUpdate: (request: DeliveryRequest) => void,
) {
  // Replace with a realtime transport (SSE, WebSocket, or backend subscription).
  return () => undefined;
}

export const deliveryStatusOrder: DeliveryStatus[] = [
  "queued",
  "accepted",
  "preparing",
  "dispatched",
  "arriving",
  "delivered",
];

export function getNextStatus(current: DeliveryStatus): DeliveryStatus {
  const index = deliveryStatusOrder.indexOf(current);
  return deliveryStatusOrder[Math.min(index + 1, deliveryStatusOrder.length - 1)];
}

export function telemetryForStatus(status: DeliveryStatus): RobotTelemetry {
  const robotStatus: RobotTelemetry["status"] =
    status === "dispatched" || status === "arriving"
      ? "moving"
      : status === "delivered"
        ? "arrived"
        : status === "preparing"
          ? "loading"
          : "idle";

  return {
    robotId: "Vehicle 01",
    status: robotStatus,
    battery: 82,
    location: status === "arriving" ? "Near destination" : undefined,
  };
}
