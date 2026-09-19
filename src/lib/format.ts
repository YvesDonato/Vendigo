export const money = (cents: number) => new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(cents / 100);
export const priceLabel = (cents: number) => cents === 0 ? "Free" : money(cents);
export const time = (date: string) => new Date(date).toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" });
