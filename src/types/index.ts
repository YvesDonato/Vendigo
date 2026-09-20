export type RobotStatus = "available" | "selling" | "stopped" | "returning";

export interface Robot {
  id: string;
  name: string;
  status: RobotStatus;
  locationId: string;
  battery: number;
}

export interface Product {
  id: string;
  name: string;
  description: string;
  priceCents: number;
  image: string;
  color: string;
  category: "drinks" | "snacks";
  enabled?: boolean;
}

export interface InventoryItem {
  robotId: string;
  productId: string;
  compartmentId: number;
  stock: number;
  capacity: number;
}

export interface Transaction {
  id: string;
  robotId: string;
  productId: string;
  locationId: string;
  amountCents: number;
  productName?: string;
  createdAt: string;
}

export interface VenueLocation {
  id: string;
  name: string;
  shortName: string;
  demand: "high" | "medium" | "low";
}

export type RobotCommand = "stop" | "resume" | "return-to-base" | "unlock" | "retry-lock";
export type OrderStatus = "opening" | "unlocked" | "locking" | "completed" | "failed" | "lock_failed";

export interface Order {
  id: string;
  robotId: string;
  productId: string | null;
  compartmentId: number;
  sessionId: string;
  locationId: string;
  status: OrderStatus;
  closesAt: number | null;
  openedAt?: number;
  error: string | null;
}

export interface AppSnapshot {
  revision: number;
  startedAt: string;
  robots: Robot[];
  products: Product[];
  inventory: InventoryItem[];
  locations: VenueLocation[];
  transactions: Transaction[];
  activeOrders: Order[];
  qrScans: number;
  purchasingSessions: number;
}
