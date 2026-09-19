export type Item = {
  id: string;
  name: string;
  description: string;
  image: string;
  category?: string;
  available: boolean;
  quantityAvailable?: number;
};

export type VenueLocation = {
  id: string;
  name: string;
  description?: string;
};

export type DeliveryStatus =
  | "queued"
  | "accepted"
  | "preparing"
  | "dispatched"
  | "arriving"
  | "delivered";

export type DeliveryRequest = {
  id: string;
  items: Array<{ itemId: string; quantity: number }>;
  locationId: string;
  locationLabel: string;
  status: DeliveryStatus;
  queuePosition?: number;
  etaMinutes?: number;
  createdAt: string;
  statusUpdatedAt: string;
};

export type RobotTelemetry = {
  robotId: string;
  status: "idle" | "loading" | "moving" | "arrived" | "returning" | "error";
  battery?: number;
  location?: string;
};

export type Selection = Record<string, number>;

export type DraftRequest = {
  selections: Selection;
  locationId: string | null;
  locationLabel: string;
};
