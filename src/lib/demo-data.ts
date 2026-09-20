import type { AppSnapshot, Product } from "../types/index.ts";

export const products: Product[] = [
  { id: "coke", name: "Coca-Cola", description: "The original. Ice cold.", priceCents: 100, image: "/products/coke.svg", color: "#da433c", category: "drinks" },
  { id: "coke-zero", name: "Coke Zero", description: "All the taste. Zero sugar.", priceCents: 100, image: "/products/coke-zero.svg", color: "#303334", category: "drinks" },
  { id: "sprite", name: "Sprite", description: "A little lemon-lime lift.", priceCents: 100, image: "/products/sprite.svg", color: "#4c9364", category: "drinks" },
  { id: "water", name: "Water", description: "A fresh start, bottled.", priceCents: 100, image: "/products/water.svg", color: "#70a3be", category: "drinks" },
  { id: "chips", name: "Chips", description: "Your next crunchy break.", priceCents: 100, image: "/products/chips.svg", color: "#d6a44a", category: "snacks" },
];

export function createSeed(): AppSnapshot {
  const now = Date.now();
  const locations: AppSnapshot["locations"] = [
    { id: "hacking", name: "Main Hacking Area", shortName: "Hacking area", demand: "high" },
    { id: "sponsors", name: "Sponsor Area", shortName: "Sponsor area", demand: "high" },
    { id: "entrance", name: "Entrance", shortName: "Entrance", demand: "medium" },
    { id: "lounge", name: "Lounge", shortName: "Lounge", demand: "low" },
  ];
  return {
    revision: 0,
    startedAt: new Date(now).toISOString(),
    robots: [{ id: "robot-001", name: "Vendigo #1", status: "available", locationId: "hacking", battery: 74 }],
    products: products.map((product) => ({ ...product, enabled: true })),
    inventory: products.map((product, i) => ({ robotId: "robot-001", productId: product.id, compartmentId: i + 1, stock: [8, 4, 7, 9, 6][i], capacity: 12 })),
    locations,
    transactions: [],
    activeOrders: [],
    qrScans: 0,
    purchasingSessions: 0,
  };
}
