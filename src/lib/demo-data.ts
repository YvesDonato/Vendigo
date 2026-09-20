import type { AppSnapshot, Product } from "../types/index.ts";

export const products: Product[] = [
  { id: "rice-krispies-original", name: "Rice Krispies Treats Original", description: "An original crispy treat.", priceCents: 100, image: "/products/rice-krispies-original.svg", color: "#3389c2", category: "snacks" },
  { id: "kitkat", name: "KitKat", description: "Take a little chocolate break.", priceCents: 100, image: "/products/kitkat.svg", color: "#d94138", category: "snacks" },
  { id: "hello-panda-chocolate", name: "Hello Panda Chocolate", description: "A crunchy chocolate-filled snack.", priceCents: 100, image: "/products/hello-panda-chocolate.svg", color: "#e5ba62", category: "snacks" },
  { id: "kirkland-granola-bar", name: "Kirkland Soft & Chewy Granola Bar", description: "A soft and chewy snack break.", priceCents: 100, image: "/products/kirkland-granola-bar.svg", color: "#50647b", category: "snacks" },
  { id: "biscoff-cookies", name: "Biscoff Cookies", description: "A little caramelized cookie crunch.", priceCents: 100, image: "/products/biscoff-cookies.svg", color: "#bd3e35", category: "snacks" },
  { id: "smarties", name: "Smarties", description: "A colourful little treat.", priceCents: 100, image: "/products/smarties.svg", color: "#489ac8", category: "snacks" },
  { id: "brookside-acai-blueberry", name: "Brookside Acai & Blueberry Dark Chocolate", description: "Acai and blueberry with dark chocolate.", priceCents: 100, image: "/products/brookside-acai-blueberry.svg", color: "#645178", category: "snacks" },
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
    inventory: products.map((product, i) => ({ robotId: "robot-001", productId: product.id, compartmentId: i + 1, stock: [3, 3, 2, 4, 2, 1, 1][i], capacity: 12 })),
    locations,
    transactions: [],
    activeOrders: [],
    qrScans: 0,
    purchasingSessions: 0,
  };
}
