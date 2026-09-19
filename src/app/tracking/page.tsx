"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { DeliveryStatus } from "@/components/DeliveryStatus";
import { DebugControls } from "@/components/DebugControls";
import { Header } from "@/components/Header";
import { RequestSummary } from "@/components/RequestSummary";
import { useDelivery } from "@/context/DeliveryContext";

export default function TrackingPage() {
  const router = useRouter();
  const { request, hydrated } = useDelivery();

  useEffect(() => {
    if (hydrated && !request) router.replace("/");
  }, [hydrated, request, router]);

  if (!hydrated || !request) {
    return (
      <main className="app-shell">
        <Header />
        <div className="page-loader"><span className="button-loader" /> Loading request</div>
      </main>
    );
  }

  const selections = Object.fromEntries(
    request.items.map(({ itemId, quantity }) => [itemId, quantity]),
  );

  return (
    <main className="app-shell tracking-page">
      <Header />
      <div className="page-content tracking-content">
        <DeliveryStatus request={request} />
        <RequestSummary
          selections={selections}
          locationLabel={request.locationLabel}
        />
      </div>
      <DebugControls />
    </main>
  );
}
