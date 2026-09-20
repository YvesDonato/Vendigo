import { Storefront } from "@/components/storefront/storefront";
import { notFound } from "next/navigation";
import { getStore } from "@/lib/server/runtime";

export const dynamic = "force-dynamic";
export const metadata = { title: "Your little break" };

export default async function ShopPage({ params }: { params: Promise<{ robotId: string }> }) {
  const { robotId } = await params;
  if (!getStore().snapshot().robots.some((robot) => robot.id === robotId)) notFound();
  return <Storefront robotId={robotId} />;
}
