import Link from "next/link";
import { Brand } from "@/components/brand";

export default function NotFound() {
  return <main className="loading-screen"><Brand /><h1>Storefront not found</h1><p>Check the QR code, or visit the demo storefront.</p><Link href="/shop/robot-001" className="button button-primary">Open storefront →</Link></main>;
}
