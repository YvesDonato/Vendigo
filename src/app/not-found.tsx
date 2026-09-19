import Link from "next/link";
import { Brand } from "@/components/brand";

export default function NotFound() {
  return <main className="loading-screen"><Brand /><span className="eyebrow">A LITTLE OFF COURSE</span><h1>This Hawk hasn’t landed yet.</h1><p>Check the QR code on your robot, or visit our demo storefront.</p><Link href="/shop/robot-001" className="button button-primary">Visit Hawk #1 →</Link></main>;
}
